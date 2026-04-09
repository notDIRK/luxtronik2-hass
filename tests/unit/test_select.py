"""Unit tests for the Luxtronik select platform.

Validates value maps, entity description invariants, SG-Ready mode map consistency,
and translation key alignment with strings.json. All tests are pure Python -- no
Home Assistant runtime required.

Strategy: Uses ast.literal_eval to extract pure-Python constants (dicts, tuples)
from select.py without triggering HA runtime imports. This is necessary because
the HA version in the test environment does not export DeviceInfo from
homeassistant.helpers.device_registry (older HA installation). The data structures
tested here (MODE_OPTIONS, SG_READY_OPTIONS, SG_READY_MODE_MAP, SELECT_DESCRIPTIONS)
are pure Python with no HA dependencies and can be safely evaluated.

Test coverage:
- CTRL-01: HeatingMode/HotWaterMode value maps and description indices (D-07, D-08)
- CTRL-02: SG-Ready mode map matches proxy sg_ready.py, dual-parameter structure (D-10, D-11)
- D-23: Translation keys in value maps match strings.json entity.select state keys
"""

from __future__ import annotations

import ast
import json
import sys
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Path setup
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SELECT_PATH = _REPO_ROOT / "custom_components" / "luxtronik2_modbus_proxy" / "select.py"
_STRINGS_PATH = _REPO_ROOT / "custom_components" / "luxtronik2_modbus_proxy" / "strings.json"
_SG_READY_PATH = _REPO_ROOT / "src" / "luxtronik2_modbus_proxy" / "sg_ready.py"

# ---------------------------------------------------------------------------
# AST-based extraction of pure-Python constants from select.py
# ---------------------------------------------------------------------------


def _extract_assign(source: str, name: str):
    """Extract the value of a module-level assignment by variable name using ast.

    Parses the source string and finds the first Assign or AnnAssign node where
    the target matches the given name. Returns the evaluated value using
    ast.literal_eval. Handles both plain assignments and annotated assignments
    (e.g., ``MODE_OPTIONS: dict[int, str] = {...}``).

    Args:
        source: Python source code string.
        name: Variable name to find (e.g., 'MODE_OPTIONS').

    Returns:
        The Python value of the assignment.

    Raises:
        KeyError: If the variable name is not found.
        ValueError: If the value cannot be parsed by ast.literal_eval.
    """
    tree = ast.parse(source)
    for node in ast.walk(tree):
        # Plain assignment: MODE_OPTIONS = {...}
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == name:
                    return ast.literal_eval(node.value)
        # Annotated assignment: MODE_OPTIONS: dict[int, str] = {...}
        if isinstance(node, ast.AnnAssign):
            if isinstance(node.target, ast.Name) and node.target.id == name:
                if node.value is not None:
                    return ast.literal_eval(node.value)
    raise KeyError(f"{name!r} not found in source")


def _extract_class_field_default(source: str, class_name: str, field_name: str):
    """Extract default value of a field in a class body via ast.

    Args:
        source: Python source code string.
        class_name: Name of the class to inspect.
        field_name: Name of the field assignment in the class body.

    Returns:
        The default value of the field.

    Raises:
        KeyError: If class or field is not found.
    """
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            for item in node.body:
                if isinstance(item, ast.AnnAssign):
                    if isinstance(item.target, ast.Name) and item.target.id == field_name:
                        if item.value is not None:
                            return ast.literal_eval(item.value)
    raise KeyError(f"Field {field_name!r} not found in class {class_name!r}")


# Load select.py source once
_SELECT_SOURCE = _SELECT_PATH.read_text()

# Extract pure-Python constants
MODE_OPTIONS: dict[int, str] = _extract_assign(_SELECT_SOURCE, "MODE_OPTIONS")
MODE_REVERSE: dict[str, int] = {v: k for k, v in MODE_OPTIONS.items()}
SG_READY_OPTIONS: dict[int, str] = _extract_assign(_SELECT_SOURCE, "SG_READY_OPTIONS")
SG_READY_REVERSE: dict[str, int] = {v: k for k, v in SG_READY_OPTIONS.items()}
SG_READY_MODE_MAP: dict[int, dict[int, int]] = _extract_assign(_SELECT_SOURCE, "SG_READY_MODE_MAP")

# Extract SELECT_DESCRIPTIONS key/lux_index/is_sg_ready values using class inspection
# We parse the SELECT_DESCRIPTIONS tuple from the ast to get structured data
def _extract_select_descriptions(source: str) -> list[dict]:
    """Extract SELECT_DESCRIPTIONS entries from select.py source.

    Parses the SELECT_DESCRIPTIONS tuple (plain or annotated assignment) and
    returns a list of dicts with key, lux_index, and is_sg_ready fields
    extracted from keyword arguments.

    Args:
        source: Python source code of select.py.

    Returns:
        List of dicts with description fields.
    """
    _FIELDS = ("key", "lux_index", "is_sg_ready")

    def _parse_tuple(value_node: ast.expr) -> list[dict]:
        if not isinstance(value_node, ast.Tuple):
            return []
        descs = []
        for elt in value_node.elts:
            if isinstance(elt, ast.Call):
                d: dict = {}
                for kw in elt.keywords:
                    if kw.arg in _FIELDS:
                        d[kw.arg] = ast.literal_eval(kw.value)
                descs.append(d)
        return descs

    tree = ast.parse(source)
    for node in ast.walk(tree):
        # Plain assignment: SELECT_DESCRIPTIONS = (...)
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "SELECT_DESCRIPTIONS":
                    return _parse_tuple(node.value)
        # Annotated assignment: SELECT_DESCRIPTIONS: tuple[...] = (...)
        if isinstance(node, ast.AnnAssign):
            if (isinstance(node.target, ast.Name)
                    and node.target.id == "SELECT_DESCRIPTIONS"
                    and node.value is not None):
                return _parse_tuple(node.value)
    return []


SELECT_DESCRIPTIONS_DATA = _extract_select_descriptions(_SELECT_SOURCE)

# Load proxy sg_ready.py SG_READY_MODE_MAP for cross-validation
_SG_READY_SOURCE = _SG_READY_PATH.read_text()
PROXY_SG_READY_MODE_MAP: dict[int, dict[int, int]] = _extract_assign(
    _SG_READY_SOURCE, "SG_READY_MODE_MAP"
)


# ===========================================================================
# Tests: MODE_OPTIONS
# ===========================================================================


class TestModeOptions:
    """Tests for HeatingMode/HotWaterMode value maps."""

    def test_mode_options_has_five_entries(self) -> None:
        assert len(MODE_OPTIONS) == 5

    def test_mode_options_keys_are_0_to_4(self) -> None:
        assert set(MODE_OPTIONS.keys()) == {0, 1, 2, 3, 4}

    def test_mode_options_values(self) -> None:
        expected = {"automatic", "second_heatsource", "party", "holidays", "off"}
        assert set(MODE_OPTIONS.values()) == expected

    def test_mode_reverse_is_exact_inverse(self) -> None:
        for raw, key in MODE_OPTIONS.items():
            assert MODE_REVERSE[key] == raw

    def test_mode_reverse_roundtrip(self) -> None:
        for raw in range(5):
            assert MODE_REVERSE[MODE_OPTIONS[raw]] == raw


# ===========================================================================
# Tests: SG_READY_OPTIONS
# ===========================================================================


class TestSgReadyOptions:
    """Tests for SG-Ready value maps and mode map."""

    def test_sg_ready_options_has_four_entries(self) -> None:
        assert len(SG_READY_OPTIONS) == 4

    def test_sg_ready_options_keys_are_0_to_3(self) -> None:
        assert set(SG_READY_OPTIONS.keys()) == {0, 1, 2, 3}

    def test_sg_ready_reverse_is_exact_inverse(self) -> None:
        for mode, key in SG_READY_OPTIONS.items():
            assert SG_READY_REVERSE[key] == mode

    def test_sg_ready_mode_map_matches_proxy(self) -> None:
        """SG_READY_MODE_MAP in select.py must match the proxy's sg_ready.py."""
        assert SG_READY_MODE_MAP == PROXY_SG_READY_MODE_MAP

    def test_sg_ready_mode_map_writes_params_3_and_4(self) -> None:
        """Every SG-Ready mode must write both parameter 3 and parameter 4."""
        for mode, param_map in SG_READY_MODE_MAP.items():
            assert 3 in param_map, f"Mode {mode} missing parameter 3"
            assert 4 in param_map, f"Mode {mode} missing parameter 4"


# ===========================================================================
# Tests: SELECT_DESCRIPTIONS
# ===========================================================================


class TestSelectDescriptions:
    """Tests for SELECT_DESCRIPTIONS structural invariants."""

    def test_description_count(self) -> None:
        assert len(SELECT_DESCRIPTIONS_DATA) == 3

    def test_heating_mode_description(self) -> None:
        desc = next(d for d in SELECT_DESCRIPTIONS_DATA if d.get("key") == "heating_mode")
        assert desc["lux_index"] == 3
        assert desc.get("is_sg_ready", False) is False

    def test_hot_water_mode_description(self) -> None:
        desc = next(d for d in SELECT_DESCRIPTIONS_DATA if d.get("key") == "hot_water_mode")
        assert desc["lux_index"] == 4
        assert desc.get("is_sg_ready", False) is False

    def test_sg_ready_description(self) -> None:
        desc = next(d for d in SELECT_DESCRIPTIONS_DATA if d.get("key") == "sg_ready")
        assert desc.get("is_sg_ready") is True

    def test_all_descriptions_have_unique_keys(self) -> None:
        keys = [d.get("key") for d in SELECT_DESCRIPTIONS_DATA]
        assert len(keys) == len(set(keys))


# ===========================================================================
# Tests: Translation alignment
# ===========================================================================


class TestSelectTranslationAlignment:
    """Verify translation keys in value maps match strings.json."""

    @pytest.fixture()
    def strings(self) -> dict:
        return json.loads(_STRINGS_PATH.read_text())

    def test_heating_mode_keys_in_strings(self, strings: dict) -> None:
        state_keys = set(strings["entity"]["select"]["heating_mode"]["state"].keys())
        option_keys = set(MODE_OPTIONS.values())
        assert option_keys == state_keys

    def test_hot_water_mode_keys_in_strings(self, strings: dict) -> None:
        state_keys = set(strings["entity"]["select"]["hot_water_mode"]["state"].keys())
        option_keys = set(MODE_OPTIONS.values())
        assert option_keys == state_keys

    def test_sg_ready_keys_in_strings(self, strings: dict) -> None:
        state_keys = set(strings["entity"]["select"]["sg_ready"]["state"].keys())
        option_keys = set(SG_READY_OPTIONS.values())
        assert option_keys == state_keys
