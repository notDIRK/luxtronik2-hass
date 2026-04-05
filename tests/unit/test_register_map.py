"""Unit tests for register definitions and RegisterMap.

Tests verify the full register definition databases and the RegisterMap class
that translates between Modbus wire addresses and Luxtronik parameter IDs.
Includes backward-compatible tests for Phase 1 curated entries plus new Phase 2
tests for visibility support and updated block sizes.
"""

import pytest

from luxtronik2_modbus_proxy.register_definitions.parameters import HOLDING_REGISTERS
from luxtronik2_modbus_proxy.register_definitions.calculations import INPUT_REGISTERS
from luxtronik2_modbus_proxy.register_map import RegisterMap, RegisterEntry


# --- Register definition tests (backward compatible) ---


def test_holding_registers_has_expected_entries():
    """HOLDING_REGISTERS dict has entries at keys 3, 4, 105 with correct luxtronik IDs."""
    assert 3 in HOLDING_REGISTERS
    assert 4 in HOLDING_REGISTERS
    assert 105 in HOLDING_REGISTERS
    assert HOLDING_REGISTERS[3].luxtronik_id == "ID_Ba_Hz_akt"
    assert HOLDING_REGISTERS[4].luxtronik_id == "ID_Ba_Bw_akt"
    assert HOLDING_REGISTERS[105].luxtronik_id == "ID_Soll_BWS_akt"


def test_input_registers_has_expected_entries():
    """INPUT_REGISTERS dict has entries at keys 10, 11, 15, 17, 80, 257 with correct luxtronik IDs."""
    assert 10 in INPUT_REGISTERS
    assert 11 in INPUT_REGISTERS
    assert 15 in INPUT_REGISTERS
    assert 17 in INPUT_REGISTERS
    assert 80 in INPUT_REGISTERS
    assert 257 in INPUT_REGISTERS
    assert INPUT_REGISTERS[10].luxtronik_id == "ID_WEB_Temperatur_TVL"
    assert INPUT_REGISTERS[11].luxtronik_id == "ID_WEB_Temperatur_TRL"
    assert INPUT_REGISTERS[15].luxtronik_id == "ID_WEB_Temperatur_TA"
    assert INPUT_REGISTERS[17].luxtronik_id == "ID_WEB_Temperatur_TBW"
    assert INPUT_REGISTERS[80].luxtronik_id == "ID_WEB_WP_BZ_akt"
    assert INPUT_REGISTERS[257].luxtronik_id == "Heat_Output"


# --- RegisterMap lookup tests (backward compatible) ---


def test_get_holding_entry_returns_correct_entry():
    """RegisterMap.get_holding_entry(3) returns RegisterEntry with correct luxtronik_id and writable=True."""
    reg_map = RegisterMap()
    entry = reg_map.get_holding_entry(3)
    assert entry is not None
    assert isinstance(entry, RegisterEntry)
    assert entry.luxtronik_id == "ID_Ba_Hz_akt"
    assert entry.writable is True


def test_get_input_entry_returns_correct_entry():
    """RegisterMap.get_input_entry(10) returns RegisterEntry with correct luxtronik_id."""
    reg_map = RegisterMap()
    entry = reg_map.get_input_entry(10)
    assert entry is not None
    assert isinstance(entry, RegisterEntry)
    assert entry.luxtronik_id == "ID_WEB_Temperatur_TVL"


def test_get_holding_entry_returns_none_for_unmapped():
    """RegisterMap.get_holding_entry(9999) returns None for unmapped address."""
    reg_map = RegisterMap()
    assert reg_map.get_holding_entry(9999) is None


def test_is_writable_true_for_writable_address():
    """RegisterMap.is_writable(3) returns True for a writable holding register."""
    reg_map = RegisterMap()
    assert reg_map.is_writable(3) is True


def test_is_writable_false_for_unmapped():
    """RegisterMap.is_writable(9999) returns False for an unmapped address."""
    reg_map = RegisterMap()
    assert reg_map.is_writable(9999) is False


# --- Write validation tests (backward compatible) ---


def test_validate_write_value_valid_heating_mode():
    """RegisterMap.validate_write_value(3, 0) returns True for valid HeatingMode value."""
    reg_map = RegisterMap()
    assert reg_map.validate_write_value(3, 0) is True


def test_validate_write_value_invalid_heating_mode():
    """RegisterMap.validate_write_value(3, 99) returns False for out-of-range HeatingMode."""
    reg_map = RegisterMap()
    assert reg_map.validate_write_value(3, 99) is False


def test_validate_write_value_valid_dhw_setpoint():
    """RegisterMap.validate_write_value(105, 450) returns True for valid DHW setpoint (45.0C)."""
    reg_map = RegisterMap()
    assert reg_map.validate_write_value(105, 450) is True


def test_validate_write_value_dhw_setpoint_below_min():
    """RegisterMap.validate_write_value(105, 100) returns False for value below min (10.0C < 30C min)."""
    reg_map = RegisterMap()
    assert reg_map.validate_write_value(105, 100) is False


def test_validate_write_value_dhw_setpoint_above_max():
    """RegisterMap.validate_write_value(105, 700) returns False for value above max (70.0C > 65C max)."""
    reg_map = RegisterMap()
    assert reg_map.validate_write_value(105, 700) is False


# --- Block size tests (updated for Phase 2) ---


def test_register_map_input_block_size():
    """RegisterMap input_block_size is 1355 to cover calculations (0-259) and visibilities (1000-1354)."""
    reg_map = RegisterMap()
    assert reg_map.input_block_size == 1355


def test_register_map_holding_block_size():
    """RegisterMap holding_block_size is 5001 to accommodate SG-ready virtual register at 5000."""
    reg_map = RegisterMap()
    assert reg_map.holding_block_size == 5001


# --- Visibility lookup tests (new Phase 2) ---


def test_get_visibility_entry_returns_entry_at_1000():
    """RegisterMap.get_visibility_entry(1000) returns a valid RegisterEntry."""
    reg_map = RegisterMap()
    entry = reg_map.get_visibility_entry(1000)
    assert entry is not None
    assert isinstance(entry, RegisterEntry)
    assert entry.address == 1000
    assert entry.writable is False


def test_get_visibility_entry_returns_entry_at_1354():
    """RegisterMap.get_visibility_entry(1354) returns a valid RegisterEntry."""
    reg_map = RegisterMap()
    entry = reg_map.get_visibility_entry(1354)
    assert entry is not None
    assert isinstance(entry, RegisterEntry)
    assert entry.address == 1354
    assert entry.writable is False


def test_get_visibility_entry_returns_none_for_out_of_range():
    """RegisterMap.get_visibility_entry(999) returns None for address below visibility range."""
    reg_map = RegisterMap()
    assert reg_map.get_visibility_entry(999) is None


def test_all_visibility_addresses_count():
    """RegisterMap.all_visibility_addresses() returns exactly 355 addresses."""
    reg_map = RegisterMap()
    addrs = reg_map.all_visibility_addresses()
    assert len(addrs) == 355


def test_all_visibility_addresses_range():
    """RegisterMap.all_visibility_addresses() spans 1000-1354."""
    reg_map = RegisterMap()
    addrs = reg_map.all_visibility_addresses()
    assert min(addrs) == 1000
    assert max(addrs) == 1354


def test_visibility_entries_are_read_only():
    """All visibility entries returned by get_visibility_entry() have writable=False."""
    reg_map = RegisterMap()
    for addr in reg_map.all_visibility_addresses():
        entry = reg_map.get_visibility_entry(addr)
        assert entry is not None
        assert entry.writable is False, f"address {addr}: expected writable=False"
