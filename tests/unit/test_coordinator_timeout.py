"""Tests for the ha-005 timeout hardening of the Luxtronik coordinator.

Two layers, neither of which imports Home Assistant or the ``luxtronik``
library (the test environment cannot import either — see the module docstrings
in test_number.py / test_select.py):

1. A real-socket behavioural test that reproduces the ha-005 failure mode — a
   server that accepts the TCP connection and then stays silent forever — and
   asserts that a socket carrying a timeout (the mechanism used by
   ``coordinator._socket_default_timeout``) raises instead of blocking forever.

2. AST/source structural guards asserting that coordinator.py wraps both the
   read and the write in ``asyncio.timeout(...)`` and bounds the library socket
   via ``_socket_default_timeout``, and that smart_energy.py sets its boost/pause
   state before issuing the write and guards against unbounded task stacking.
"""

from __future__ import annotations

import ast
import socket
import threading
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_COMPONENT = _REPO_ROOT / "custom_components" / "luxtronik2_hass"
_COORDINATOR_PATH = _COMPONENT / "coordinator.py"
_SMART_ENERGY_PATH = _COMPONENT / "smart_energy.py"
_CONST_PATH = _COMPONENT / "const.py"


# ---------------------------------------------------------------------------
# Layer 1: real-socket behaviour — a silent server must not block forever.
# ---------------------------------------------------------------------------


class _SilentServer:
    """A TCP server that accepts a connection and then never sends anything.

    This is exactly the ha-005 trigger: the peer accepts the socket (so
    ``connect`` succeeds in milliseconds) but then stays mute, so a timeout-less
    ``recv`` blocks indefinitely.
    """

    def __init__(self) -> None:
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._sock.bind(("127.0.0.1", 0))
        self._sock.listen(1)
        self.port: int = self._sock.getsockname()[1]
        self._held: list[socket.socket] = []
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._serve, daemon=True)
        self._thread.start()

    def _serve(self) -> None:
        self._sock.settimeout(0.2)
        while not self._stop.is_set():
            try:
                conn, _ = self._sock.accept()
            except (TimeoutError, OSError):
                continue
            # Hold the connection open but send nothing — the mute peer.
            self._held.append(conn)

    def close(self) -> None:
        self._stop.set()
        self._thread.join(timeout=2)
        for conn in self._held:
            conn.close()
        self._sock.close()


@pytest.fixture
def silent_server() -> _SilentServer:
    server = _SilentServer()
    yield server
    server.close()


def test_recv_without_timeout_premise(silent_server: _SilentServer) -> None:
    """Sanity: connecting to the silent server succeeds fast (the trap)."""
    with socket.create_connection(
        ("127.0.0.1", silent_server.port), timeout=1
    ) as conn:
        # Connection established in milliseconds — matches the ticket's note
        # that a bare TCP connect to the controller succeeds in ~5 ms.
        assert conn.fileno() != -1


def test_socket_timeout_bounds_a_silent_peer(silent_server: _SilentServer) -> None:
    """A socket with a timeout raises on recv from a mute peer (does not hang).

    This is the behaviour ``coordinator._socket_default_timeout`` grants to the
    luxtronik library's otherwise timeout-less socket. We use a short timeout so
    the test is fast; production uses const.SOCKET_TIMEOUT.
    """
    with socket.create_connection(
        ("127.0.0.1", silent_server.port), timeout=1
    ) as conn:
        conn.settimeout(0.3)
        with pytest.raises((TimeoutError, socket.timeout)):
            conn.recv(4)


def test_setdefaulttimeout_applies_to_new_sockets(
    silent_server: _SilentServer,
) -> None:
    """New sockets inherit the process default timeout (the injection mechanism).

    Mirrors ``_socket_default_timeout``: set the default, create a socket the way
    a library would (no explicit timeout), confirm recv from a mute peer raises,
    and confirm the default is restored.
    """
    previous = socket.getdefaulttimeout()
    socket.setdefaulttimeout(0.3)
    try:
        conn = socket.create_connection(("127.0.0.1", silent_server.port))
        try:
            assert conn.gettimeout() == pytest.approx(0.3)
            with pytest.raises((TimeoutError, socket.timeout)):
                conn.recv(4)
        finally:
            conn.close()
    finally:
        socket.setdefaulttimeout(previous)
    assert socket.getdefaulttimeout() == previous


# ---------------------------------------------------------------------------
# Layer 2: structural guards on the component source (no HA import).
# ---------------------------------------------------------------------------


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_const_defines_timeouts() -> None:
    """const.py defines both the socket and whole-coordinator timeouts."""
    tree = ast.parse(_read(_CONST_PATH))
    assigned = {
        t.id
        for node in tree.body
        if isinstance(node, ast.Assign)
        for t in node.targets
        if isinstance(t, ast.Name)
    }
    assert "SOCKET_TIMEOUT" in assigned
    assert "COORDINATOR_TIMEOUT" in assigned


def test_coordinator_wraps_read_and_write_in_asyncio_timeout() -> None:
    """Both async read and write paths use asyncio.timeout(COORDINATOR_TIMEOUT)."""
    src = _read(_COORDINATOR_PATH)
    # Two occurrences: one in _async_update_data, one in async_write_parameters.
    assert src.count("asyncio.timeout(COORDINATOR_TIMEOUT)") >= 2
    # UpdateFailed is raised on the read timeout so entities flip to unavailable.
    assert "UpdateFailed" in src


def test_coordinator_bounds_library_socket() -> None:
    """Both _sync_read and _sync_write wrap the blocking lux call in a timeout."""
    src = _read(_COORDINATOR_PATH)
    assert "_socket_default_timeout(SOCKET_TIMEOUT)" in src
    # Guard: the context manager must wrap the actual blocking calls.
    assert src.count("_socket_default_timeout(SOCKET_TIMEOUT)") >= 2


def _ordered_in_body(body: list[ast.stmt], flag_attr: str) -> bool:
    """Return True if ``self.<flag_attr> = ...`` precedes the first await-write.

    Confirms the ha-005 "set state before the write" ordering.
    """
    flag_line: int | None = None
    write_line: int | None = None
    for node in ast.walk(ast.Module(body=body, type_ignores=[])):
        if (
            isinstance(node, ast.Assign)
            and any(
                isinstance(t, ast.Attribute) and t.attr == flag_attr
                for t in node.targets
            )
            and flag_line is None
        ):
            flag_line = node.lineno
        if isinstance(node, ast.Await):
            call = node.value
            if isinstance(call, ast.Call):
                func = call.func
                name = getattr(func, "attr", getattr(func, "id", ""))
                if name in ("_set_hot_water_temp", "_set_heating_mode") and (
                    write_line is None
                ):
                    write_line = node.lineno
    return flag_line is not None and write_line is not None and flag_line < write_line


def test_smart_energy_sets_state_before_write() -> None:
    """_activate_boost / _deactivate_boost set _boost_active before the write."""
    tree = ast.parse(_read(_SMART_ENERGY_PATH))
    funcs = {
        n.name: n
        for n in ast.walk(tree)
        if isinstance(n, ast.AsyncFunctionDef)
    }
    assert _ordered_in_body(funcs["_activate_boost"].body, "_boost_active")
    assert _ordered_in_body(funcs["_deactivate_boost"].body, "_boost_active")


def test_smart_energy_guards_task_stacking() -> None:
    """A single evaluation lock prevents unbounded task stacking (ha-005)."""
    src = _read(_SMART_ENERGY_PATH)
    assert "_eval_lock" in src
    assert "_guarded_evaluate" in src
    assert ".locked()" in src


def test_smart_energy_recovers_setpoint_on_start() -> None:
    """Startup reconciliation of a stale boost setpoint exists (ha-003)."""
    src = _read(_SMART_ENERGY_PATH)
    assert "_recover_setpoint_on_start" in src
