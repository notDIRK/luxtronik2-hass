"""Coordinator for the Luxtronik 2.0 (Home Assistant) integration.

Implements a DataUpdateCoordinator that polls the Luxtronik 2.0 heat pump
controller using the connect-per-call pattern. Each poll cycle creates a new
luxtronik.Luxtronik instance, reads all data and write parameter updates,
extracts raw integer values, and discards the instance — releasing the single
TCP connection on port 8889 so that other tools (e.g., the BenPru/luxtronik HA
integration) can coexist.

Write operations use the same connect-per-call pattern and are serialized via
the same asyncio.Lock as reads. Per-parameter rate limiting (CTRL-04) enforces
a 60-second minimum interval between writes to the same parameter index, protecting
the Luxtronik controller NAND flash from excessive write cycles.

Architecture constraints enforced here:
- ARCH-01: Connect-per-call pattern via ``luxtronik.Luxtronik.__new__`` to avoid
  the auto-read() call in Luxtronik.__init__.
- ARCH-02: All blocking luxtronik calls run via ``hass.async_add_executor_job``
  to avoid stalling the HA asyncio event loop.
- ARCH-03: A single ``asyncio.Lock`` serializes all read and write operations,
  enforcing the Luxtronik 2.0 single-connection constraint.
"""

from __future__ import annotations

import asyncio
import contextlib
from datetime import datetime, timedelta
import logging
import socket
import time
from collections.abc import Iterator

import luxtronik

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .const import (
    COORDINATOR_TIMEOUT,
    DEFAULT_POLL_INTERVAL,
    DEFAULT_PORT,
    DOMAIN,
    SOCKET_TIMEOUT,
    WRITE_RATE_LIMIT_SECONDS,
)

_LOGGER = logging.getLogger(__name__)


@contextlib.contextmanager
def _socket_default_timeout(timeout: float) -> Iterator[None]:
    """Temporarily set the process-wide default socket timeout.

    ha-005: the pinned ``luxtronik==0.3.14`` library opens its TCP socket and
    issues blocking ``recv()`` calls with no timeout, so a silently-dropped
    connection (observed: 35 h hang) blocks the executor thread forever. The
    library exposes no timeout parameter, so we bound its sockets at the stdlib
    level: ``socket.setdefaulttimeout`` applies to every socket created *after*
    the call, which is exactly when the library builds its connection inside
    ``read()``/``write()``. This depends only on documented stdlib behaviour,
    not on the library's private internals (which cannot be verified here).

    The whole read/write coroutine is independently bounded by
    ``asyncio.timeout(COORDINATOR_TIMEOUT)``; this socket timeout additionally
    unblocks the orphaned executor thread so it is returned to the pool instead
    of leaking.

    Runs inside the executor thread only. The prior default is restored on exit.
    """
    previous = socket.getdefaulttimeout()
    socket.setdefaulttimeout(timeout)
    try:
        yield
    finally:
        socket.setdefaulttimeout(previous)


class LuxtronikCoordinator(DataUpdateCoordinator[dict]):
    """Coordinator for Luxtronik 2.0 heat pump data.

    Implements the connect-per-call pattern: creates a new luxtronik.Luxtronik
    instance for each poll cycle and discards it after reading. This releases
    the single TCP connection on port 8889 between poll cycles, allowing the
    BenPru/luxtronik HA integration to coexist on the same controller. (ARCH-01)

    All luxtronik library calls run in the HA executor thread pool via
    ``hass.async_add_executor_job`` to avoid blocking the HA event loop. (ARCH-02)

    A single asyncio.Lock serializes all read and write operations to enforce
    the Luxtronik 2.0 single-connection constraint — only one TCP connection
    is permitted at any time. (ARCH-03)

    coordinator.data structure (D-05):
        {
            "parameters": dict[int, int],    # Luxtronik parameter index -> raw int value
            "calculations": dict[int, int],  # Luxtronik calculation index -> raw int value
        }
    """

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: ConfigEntry,
        host: str,
        port: int = DEFAULT_PORT,
    ) -> None:
        """Initialize the LuxtronikCoordinator.

        Args:
            hass: The Home Assistant instance.
            config_entry: The config entry this coordinator is associated with.
            host: Hostname or IP address of the Luxtronik 2.0 controller.
            port: TCP port of the Luxtronik binary protocol server (default 8889).
        """
        self._host = host
        self._port = port
        # ARCH-03: Single lock serializes all TCP access. Created here so Phase 7
        # write methods acquire the same lock without restructuring the coordinator.
        self._lock = asyncio.Lock()
        # CTRL-04, D-04: Per-parameter write timestamp tracking for rate limiting.
        # Same pattern as PollingEngine._write_timestamps in the proxy codebase.
        self._write_timestamps: dict[int, float] = {}
        # ha-005: timestamp of the last fully successful read. Exposed as a
        # diagnostic sensor ("Letzte erfolgreiche Abfrage") so a stalled poll is
        # observable even before entities flip to unavailable.
        self.last_successful_update: datetime | None = None

        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            config_entry=config_entry,
            update_interval=timedelta(seconds=DEFAULT_POLL_INTERVAL),
        )

    async def _async_update_data(self) -> dict:
        """Fetch all data from the Luxtronik controller.

        Acquires the serialization lock (ARCH-03), then dispatches the blocking
        read to the executor thread pool (ARCH-02). Creates a fresh Luxtronik
        instance for each call (ARCH-01) and discards it after value extraction.

        Returns:
            A dict with keys ``"parameters"`` and ``"calculations"``, each mapping
            Luxtronik indices to raw integer values (D-05).

        Raises:
            UpdateFailed: On any exception from the luxtronik library or network,
                causing the coordinator to mark entities unavailable and triggering
                HA's built-in retry backoff.
        """
        async with self._lock:  # ARCH-03: serialize concurrent read/write access
            try:
                # ha-005: whole-poll ceiling. On timeout the coroutine returns
                # (raising UpdateFailed), the lock is released by the context
                # manager, last_update_success flips to False → entities become
                # unavailable, and HA reschedules the next refresh — recovery
                # without a restart.
                async with asyncio.timeout(COORDINATOR_TIMEOUT):
                    data = await self.hass.async_add_executor_job(self._sync_read)
            except TimeoutError as err:
                raise UpdateFailed(
                    f"Timeout after {COORDINATOR_TIMEOUT}s communicating with "
                    f"Luxtronik at {self._host}"
                ) from err
            except Exception as err:
                raise UpdateFailed(
                    f"Error communicating with Luxtronik at {self._host}: {err}"
                ) from err
        self.last_successful_update = dt_util.utcnow()
        return data

    def _sync_read(self) -> dict:
        """Read all parameters and calculations from the Luxtronik controller.

        Runs in the HA executor thread pool — blocking socket I/O is permitted here.

        Uses ``luxtronik.Luxtronik.__new__`` followed by manual attribute
        initialization to avoid the auto-read call in ``Luxtronik.__init__``.
        The ``Luxtronik`` constructor unconditionally calls ``self.read()`` as its
        last operation, which would block the executor thread before attributes are
        set. By using ``__new__``, we control exactly when the read occurs. (ARCH-01)

        After calling ``lux.read()``, extracts raw integer values for all
        parameters and calculations using ``to_heatpump()`` — the wire-format
        integers consumed by Modbus clients and HA entity platforms. (D-05)

        Returns:
            A dict matching the D-05 structure:
            ``{"parameters": dict[int, int], "calculations": dict[int, int]}``
        """
        # ARCH-01: Use __new__ to skip Luxtronik.__init__ auto-read.
        # Luxtronik.__init__ calls self.read() unconditionally with no opt-out.
        # This is the same pattern used in luxtronik_client.py (verified against
        # the live library via inspect.getsource).
        lux = luxtronik.Luxtronik.__new__(luxtronik.Luxtronik)
        lux._host = self._host
        lux._port = self._port
        lux._socket = None
        lux.calculations = luxtronik.Calculations()
        lux.parameters = luxtronik.Parameters()
        lux.visibilities = luxtronik.Visibilities()
        # ha-005: bound the library's timeout-less socket (connect + recv) so a
        # silent/half-open connection cannot block this executor thread forever.
        with _socket_default_timeout(SOCKET_TIMEOUT):
            lux.read()  # blocking — OK, we are running in the executor thread

        # Extract raw integer values for all parameters (read/write Luxtronik params).
        # lux.parameters.parameters is a dict[int, TypedParam] where values are typed
        # objects (Celsius, HeatingMode, etc.) with .value and .to_heatpump() methods.
        # to_heatpump() converts back to wire-format integer (e.g., 550 for 55.0 degC).
        parameters: dict[int, int] = {}
        for idx, param in lux.parameters.parameters.items():
            if param is not None and hasattr(param, "to_heatpump"):
                try:
                    raw = param.to_heatpump(param.value)
                    if raw is not None:
                        parameters[idx] = int(raw)
                except (TypeError, ValueError, AttributeError):
                    pass

        # Extract raw integer values for all calculations (read-only Luxtronik data).
        # Same structure: dict[int, TypedCalc] with .value and .to_heatpump().
        calculations: dict[int, int] = {}
        for idx, calc in lux.calculations.calculations.items():
            if calc is not None and hasattr(calc, "to_heatpump"):
                try:
                    raw = calc.to_heatpump(calc.value)
                    if raw is not None:
                        calculations[idx] = int(raw)
                except (TypeError, ValueError, AttributeError):
                    pass

        _LOGGER.debug(
            "Luxtronik read complete: %d parameters, %d calculations",
            len(parameters),
            len(calculations),
        )
        return {"parameters": parameters, "calculations": calculations}

    async def async_write_parameter(self, index: int, value: int) -> None:
        """Write a single parameter to the Luxtronik controller.

        Convenience wrapper around async_write_parameters for single-parameter
        writes. Acquires the lock, checks rate limit, writes, and triggers
        a coordinator refresh. (D-01)

        Args:
            index: Luxtronik parameter index (e.g., 3 for HeatingMode).
            value: Raw integer value to write (heatpump format).
        """
        await self.async_write_parameters({index: value})

    async def async_write_parameters(self, params: dict[int, int]) -> None:
        """Write multiple parameters atomically within a single lock acquisition.

        Used by SG-Ready which writes parameters 3 and 4 simultaneously (D-11, D-12).
        Rate limiting is checked per-parameter; any rate-limited parameter is
        silently skipped with a warning log (D-05). If all parameters are rate-limited,
        no write occurs and no refresh is triggered.

        Args:
            params: Dict of Luxtronik parameter index -> raw integer value to write.
        """
        async with self._lock:
            now = time.time()
            writes_to_send: dict[int, int] = {}
            for index, value in params.items():
                last_write = self._write_timestamps.get(index, 0.0)
                if now - last_write < WRITE_RATE_LIMIT_SECONDS:
                    _LOGGER.warning(
                        "Write to parameter %d rate-limited (%.1fs remaining)",
                        index,
                        WRITE_RATE_LIMIT_SECONDS - (now - last_write),
                    )
                    continue
                writes_to_send[index] = value

            if not writes_to_send:
                return

            try:
                # ha-005: bound the write the same way as the read, so a hung
                # write-confirmation cannot hold the lock forever (the original
                # 35 h hang was triggered by a Solar-Boost write).
                async with asyncio.timeout(COORDINATOR_TIMEOUT):
                    await self.hass.async_add_executor_job(
                        self._sync_write, writes_to_send
                    )
            except TimeoutError:
                _LOGGER.error(
                    "Timeout after %ds writing parameters %s to Luxtronik at %s",
                    COORDINATOR_TIMEOUT,
                    writes_to_send,
                    self._host,
                )
                raise
            except Exception as err:
                _LOGGER.error(
                    "Error writing parameters %s to Luxtronik at %s: %s",
                    writes_to_send,
                    self._host,
                    err,
                )
                raise

            # Update timestamps for accepted writes
            for index in writes_to_send:
                self._write_timestamps[index] = now

        # Trigger immediate refresh so entities reflect the new value (D-01)
        await self.async_request_refresh()

    def _sync_write(self, param_writes: dict[int, int]) -> None:
        """Write parameters to the Luxtronik controller (runs in executor).

        Creates a fresh Luxtronik instance, populates the write queue, and
        calls write(). Connect-per-call pattern — no persistent socket. (D-02, ARCH-01)

        Args:
            param_writes: Dict of Luxtronik parameter index -> raw integer value.
        """
        lux = luxtronik.Luxtronik.__new__(luxtronik.Luxtronik)
        lux._host = self._host
        lux._port = self._port
        lux._socket = None
        lux.calculations = luxtronik.Calculations()
        lux.parameters = luxtronik.Parameters()
        lux.visibilities = luxtronik.Visibilities()

        # CRITICAL: Populate the write queue BEFORE calling write().
        # The write() method reads parameters.queue synchronously at call time.
        # (Pitfall 3 from RESEARCH.md)
        lux.parameters.queue = dict(param_writes)
        # ha-005: bound the library's timeout-less socket during the write and
        # the read-back that follows it inside write().
        with _socket_default_timeout(SOCKET_TIMEOUT):
            lux.write()

        _LOGGER.info(
            "Luxtronik write complete: %s",
            {idx: val for idx, val in param_writes.items()},
        )
