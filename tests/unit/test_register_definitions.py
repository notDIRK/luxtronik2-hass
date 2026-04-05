"""Unit tests for the full Luxtronik register definition databases.

Verifies that the full parameter, calculation, and visibility databases
are built correctly from luxtronik library introspection. Tests cover:
- Database completeness (1,126 params, 251 calcs, 355 visibilities)
- Metadata correctness (writable flags, allowed_values, data_types)
- Addressing conventions (0-based for params/calcs, 1000-offset for visibilities)
- Reverse lookup dictionaries (NAME_TO_INDEX, CALC_NAME_TO_INDEX, VISI_NAME_TO_INDEX)
"""

import pytest

from luxtronik2_modbus_proxy.register_definitions.parameters import (
    HOLDING_REGISTERS,
    NAME_TO_INDEX,
    ParameterDef,
)
from luxtronik2_modbus_proxy.register_definitions.calculations import (
    INPUT_REGISTERS,
    CALC_NAME_TO_INDEX,
    CalculationDef,
)
from luxtronik2_modbus_proxy.register_definitions.visibilities import (
    VISIBILITY_REGISTERS,
    VISI_NAME_TO_INDEX,
    VisibilityDef,
)


# ============================================================================
# HOLDING_REGISTERS (parameters) tests
# ============================================================================


def test_holding_registers_count():
    """HOLDING_REGISTERS contains all 1,126 Luxtronik parameters."""
    assert len(HOLDING_REGISTERS) == 1126


def test_holding_registers_keys_span_0_to_1125():
    """HOLDING_REGISTERS keys span the full 0-1125 range with no gaps."""
    assert set(HOLDING_REGISTERS.keys()) == set(range(1126))


def test_holding_registers_writable_count():
    """Exactly 25 parameters are marked writable."""
    writable = [d for d in HOLDING_REGISTERS.values() if d.writable]
    assert len(writable) == 25


def test_holding_register_3_metadata():
    """HOLDING_REGISTERS[3] is ID_Ba_Hz_akt, writable, with correct allowed_values."""
    entry = HOLDING_REGISTERS[3]
    assert entry.luxtronik_id == "ID_Ba_Hz_akt"
    assert entry.writable is True
    assert entry.allowed_values is not None
    assert 0 in entry.allowed_values
    assert 1 in entry.allowed_values
    assert 2 in entry.allowed_values
    assert 3 in entry.allowed_values
    assert 4 in entry.allowed_values


def test_holding_register_105_metadata():
    """HOLDING_REGISTERS[105] is ID_Soll_BWS_akt and writable."""
    entry = HOLDING_REGISTERS[105]
    assert entry.luxtronik_id == "ID_Soll_BWS_akt"
    assert entry.writable is True


def test_all_holding_registers_have_non_empty_metadata():
    """Every ParameterDef has non-empty luxtronik_id, name, and data_type."""
    for address, param in HOLDING_REGISTERS.items():
        assert isinstance(param, ParameterDef), f"address {address}: not a ParameterDef"
        assert param.luxtronik_id, f"address {address}: empty luxtronik_id"
        assert param.name, f"address {address}: empty name"
        assert param.data_type, f"address {address}: empty data_type"


def test_selection_base_params_have_allowed_values():
    """Every SelectionBase-derived parameter has non-None allowed_values."""
    # HeatingMode (address 3) and HotWaterMode (address 4) are SelectionBase
    # Both must have allowed_values set
    for addr in [3, 4]:
        entry = HOLDING_REGISTERS[addr]
        assert entry.allowed_values is not None, (
            f"address {addr} ({entry.luxtronik_id}): expected allowed_values, got None"
        )
        assert len(entry.allowed_values) > 0, (
            f"address {addr} ({entry.luxtronik_id}): allowed_values is empty"
        )


def test_name_to_index_reverse_lookup():
    """NAME_TO_INDEX maps every luxtronik_id back to its wire address."""
    assert "ID_Ba_Hz_akt" in NAME_TO_INDEX
    assert NAME_TO_INDEX["ID_Ba_Hz_akt"] == 3
    assert "ID_Soll_BWS_akt" in NAME_TO_INDEX
    assert NAME_TO_INDEX["ID_Soll_BWS_akt"] == 105
    # Total count should match HOLDING_REGISTERS
    assert len(NAME_TO_INDEX) == len(HOLDING_REGISTERS)


# ============================================================================
# INPUT_REGISTERS (calculations) tests
# ============================================================================


def test_input_registers_count():
    """INPUT_REGISTERS contains all 251 Luxtronik calculations."""
    assert len(INPUT_REGISTERS) == 251


def test_input_registers_keys_within_range():
    """INPUT_REGISTERS keys are within 0-259 (the lib's key space)."""
    for key in INPUT_REGISTERS.keys():
        assert 0 <= key <= 259, f"key {key} is outside 0-259"


def test_input_registers_absent_indices():
    """Indices 82-90 are absent from INPUT_REGISTERS (None in luxtronik library)."""
    for idx in range(82, 91):
        assert idx not in INPUT_REGISTERS, f"index {idx} should be absent but is present"


def test_input_register_10_metadata():
    """INPUT_REGISTERS[10] is ID_WEB_Temperatur_TVL."""
    entry = INPUT_REGISTERS[10]
    assert entry.luxtronik_id == "ID_WEB_Temperatur_TVL"
    assert isinstance(entry, CalculationDef)


def test_calc_name_to_index_reverse_lookup():
    """CALC_NAME_TO_INDEX maps every luxtronik_id back to its wire address."""
    assert "ID_WEB_Temperatur_TVL" in CALC_NAME_TO_INDEX
    assert CALC_NAME_TO_INDEX["ID_WEB_Temperatur_TVL"] == 10
    assert len(CALC_NAME_TO_INDEX) == len(INPUT_REGISTERS)


# ============================================================================
# VISIBILITY_REGISTERS tests
# ============================================================================


def test_visibility_registers_count():
    """VISIBILITY_REGISTERS contains all 355 Luxtronik visibilities."""
    assert len(VISIBILITY_REGISTERS) == 355


def test_visibility_registers_keys_span_1000_to_1354():
    """VISIBILITY_REGISTERS keys span 1000-1354 (offset 1000 applied per D-14)."""
    keys = VISIBILITY_REGISTERS.keys()
    assert min(keys) == 1000
    assert max(keys) == 1354


def test_all_visibility_registers_are_visibility_def():
    """All VISIBILITY_REGISTERS values are VisibilityDef instances."""
    for address, visi in VISIBILITY_REGISTERS.items():
        assert isinstance(visi, VisibilityDef), (
            f"address {address}: expected VisibilityDef, got {type(visi).__name__}"
        )


def test_visi_name_to_index_reverse_lookup():
    """VISI_NAME_TO_INDEX maps every luxtronik_id back to its offset wire address."""
    # First visibility should map to 1000
    first_visi = VISIBILITY_REGISTERS[1000]
    assert first_visi.luxtronik_id in VISI_NAME_TO_INDEX
    assert VISI_NAME_TO_INDEX[first_visi.luxtronik_id] == 1000
    assert len(VISI_NAME_TO_INDEX) == len(VISIBILITY_REGISTERS)


def test_visibility_registers_have_non_empty_metadata():
    """Every VisibilityDef has non-empty luxtronik_id and name."""
    for address, visi in VISIBILITY_REGISTERS.items():
        assert visi.luxtronik_id, f"address {address}: empty luxtronik_id"
        assert visi.name, f"address {address}: empty name"
