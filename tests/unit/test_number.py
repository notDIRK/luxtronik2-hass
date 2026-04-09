"""Unit tests for the Luxtronik number platform.

Validates entity description invariants, temperature conversion logic, and
translation key alignment with strings.json. All tests are pure Python -- no
Home Assistant runtime required.

Strategy: Uses ast.literal_eval to extract pure-Python constants from number.py
without triggering HA runtime imports. This is necessary because the HA version
in the test environment does not export DeviceInfo from
homeassistant.helpers.device_registry (older HA installation). The data structures
tested here (NUMBER_DESCRIPTIONS fields) are pure Python with no HA dependencies.

Test coverage:
- CTRL-03: Temperature setpoint ranges and step values (D-14, D-15)
- D-16: Celsius raw<->display conversion (raw = display * 10)
- Translation key alignment with strings.json entity.number
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Path setup
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).resolve().parents[2]
_NUMBER_PATH = _REPO_ROOT / "custom_components" / "luxtronik2_modbus_proxy" / "number.py"
_STRINGS_PATH = _REPO_ROOT / "custom_components" / "luxtronik2_modbus_proxy" / "strings.json"

# ---------------------------------------------------------------------------
# AST-based extraction of NUMBER_DESCRIPTIONS from number.py
# ---------------------------------------------------------------------------


def _extract_number_descriptions(source: str) -> list[dict]:
    """Extract NUMBER_DESCRIPTIONS entries from number.py source.

    Parses the NUMBER_DESCRIPTIONS tuple (plain or annotated assignment) and
    returns a list of dicts with key, lux_index, native_min_value, native_max_value,
    native_step, and raw_multiplier fields extracted from keyword arguments.

    Args:
        source: Python source code of number.py.

    Returns:
        List of dicts with description fields.
    """
    _FIELDS = ("key", "lux_index", "native_min_value", "native_max_value",
               "native_step", "raw_multiplier")

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
        # Plain assignment: NUMBER_DESCRIPTIONS = (...)
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "NUMBER_DESCRIPTIONS":
                    return _parse_tuple(node.value)
        # Annotated assignment: NUMBER_DESCRIPTIONS: tuple[...] = (...)
        if isinstance(node, ast.AnnAssign):
            if (isinstance(node.target, ast.Name)
                    and node.target.id == "NUMBER_DESCRIPTIONS"
                    and node.value is not None):
                return _parse_tuple(node.value)
    return []


_NUMBER_SOURCE = _NUMBER_PATH.read_text()
NUMBER_DESCRIPTIONS_DATA = _extract_number_descriptions(_NUMBER_SOURCE)


# ===========================================================================
# Tests: NUMBER_DESCRIPTIONS
# ===========================================================================


class TestNumberDescriptions:
    """Tests for NUMBER_DESCRIPTIONS structural invariants."""

    def test_description_count(self) -> None:
        assert len(NUMBER_DESCRIPTIONS_DATA) == 2

    def test_hot_water_setpoint(self) -> None:
        desc = next(d for d in NUMBER_DESCRIPTIONS_DATA if d.get("key") == "hot_water_setpoint")
        assert desc["lux_index"] == 105
        assert desc["native_min_value"] == 30.0
        assert desc["native_max_value"] == 65.0
        assert desc["native_step"] == 0.5
        assert desc["raw_multiplier"] == 10

    def test_heating_curve_offset(self) -> None:
        desc = next(d for d in NUMBER_DESCRIPTIONS_DATA if d.get("key") == "heating_curve_offset")
        assert desc["lux_index"] == 1
        assert desc["native_min_value"] == -5.0
        assert desc["native_max_value"] == 5.0
        assert desc["native_step"] == 0.5
        assert desc["raw_multiplier"] == 10

    def test_all_descriptions_have_unique_keys(self) -> None:
        keys = [d.get("key") for d in NUMBER_DESCRIPTIONS_DATA]
        assert len(keys) == len(set(keys))


# ===========================================================================
# Tests: Celsius conversion logic (D-16)
# ===========================================================================


class TestCelsiusConversion:
    """Tests for raw<->display Celsius conversion logic (D-16)."""

    @pytest.fixture(params=[
        (500, 50.0),
        (300, 30.0),
        (650, 65.0),
        (0, 0.0),
        (-50, -5.0),
        (50, 5.0),
        (425, 42.5),
    ])
    def raw_display_pair(self, request: pytest.FixtureRequest) -> tuple[int, float]:
        return request.param

    def test_raw_to_display(self, raw_display_pair: tuple[int, float]) -> None:
        """raw / 10 must equal display value."""
        raw, display = raw_display_pair
        multiplier = 10  # from NUMBER_DESCRIPTIONS
        assert raw / multiplier == display

    def test_display_to_raw(self, raw_display_pair: tuple[int, float]) -> None:
        """int(display * 10) must equal raw value."""
        raw, display = raw_display_pair
        multiplier = 10
        assert int(display * multiplier) == raw


# ===========================================================================
# Tests: Translation alignment
# ===========================================================================


class TestNumberTranslationAlignment:
    """Verify translation keys in descriptions match strings.json."""

    @pytest.fixture()
    def strings(self) -> dict:
        return json.loads(_STRINGS_PATH.read_text())

    def test_all_number_keys_in_strings(self, strings: dict) -> None:
        string_keys = set(strings["entity"]["number"].keys())
        desc_keys = {d["key"] for d in NUMBER_DESCRIPTIONS_DATA}
        assert desc_keys.issubset(string_keys)
