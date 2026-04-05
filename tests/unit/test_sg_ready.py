"""Unit tests for sg_ready module.

Tests cover SG_READY_MODE_MAP correctness, translate_sg_ready_mode behavior
(valid modes, invalid mode rejection), and validate_sg_ready_mode helper.
"""

from __future__ import annotations

import pytest

from luxtronik2_modbus_proxy.sg_ready import (
    SG_READY_MODE_MAP,
    SG_READY_WIRE_ADDRESS,
    SG_READY_DATABLOCK_ADDRESS,
    SgReadyWrite,
    translate_sg_ready_mode,
    validate_sg_ready_mode,
)


# ---------------------------------------------------------------------------
# SG_READY_MODE_MAP correctness tests
# ---------------------------------------------------------------------------


def test_mode_map_has_four_entries() -> None:
    """Test: SG_READY_MODE_MAP contains exactly 4 entries for modes 0, 1, 2, 3."""
    assert len(SG_READY_MODE_MAP) == 4
    assert set(SG_READY_MODE_MAP.keys()) == {0, 1, 2, 3}


def test_mode_0_evu_lock_mapping() -> None:
    """Test: Mode 0 (EVU lock) maps to HeatingMode=Off(4), HotWaterMode=Off(4)."""
    assert SG_READY_MODE_MAP[0] == {3: 4, 4: 4}


def test_mode_1_normal_mapping() -> None:
    """Test: Mode 1 (Normal) maps to HeatingMode=Auto(0), HotWaterMode=Auto(0)."""
    assert SG_READY_MODE_MAP[1] == {3: 0, 4: 0}


def test_mode_2_recommended_mapping() -> None:
    """Test: Mode 2 (Recommended) maps to HeatingMode=Party(2), HotWaterMode=Auto(0)."""
    assert SG_READY_MODE_MAP[2] == {3: 2, 4: 0}


def test_mode_3_force_on_mapping() -> None:
    """Test: Mode 3 (Force on) maps to HeatingMode=Auto(0), HotWaterMode=Party(2)."""
    assert SG_READY_MODE_MAP[3] == {3: 0, 4: 2}


# ---------------------------------------------------------------------------
# Constants tests
# ---------------------------------------------------------------------------


def test_sg_ready_wire_address() -> None:
    """Test: SG_READY_WIRE_ADDRESS is 5000 (per plan D-09)."""
    assert SG_READY_WIRE_ADDRESS == 5000


def test_sg_ready_datablock_address() -> None:
    """Test: SG_READY_DATABLOCK_ADDRESS is 5001 (wire + 1)."""
    assert SG_READY_DATABLOCK_ADDRESS == 5001


# ---------------------------------------------------------------------------
# translate_sg_ready_mode tests
# ---------------------------------------------------------------------------


def test_translate_mode_0() -> None:
    """Test: translate_sg_ready_mode(0) returns EVU lock parameter writes."""
    result = translate_sg_ready_mode(0)
    assert result == {3: 4, 4: 4}


def test_translate_mode_1() -> None:
    """Test: translate_sg_ready_mode(1) returns Normal parameter writes."""
    result = translate_sg_ready_mode(1)
    assert result == {3: 0, 4: 0}


def test_translate_mode_2() -> None:
    """Test: translate_sg_ready_mode(2) returns Recommended parameter writes."""
    result = translate_sg_ready_mode(2)
    assert result == {3: 2, 4: 0}


def test_translate_mode_3() -> None:
    """Test: translate_sg_ready_mode(3) returns Force on parameter writes."""
    result = translate_sg_ready_mode(3)
    assert result == {3: 0, 4: 2}


def test_translate_invalid_mode_4_raises() -> None:
    """Test: translate_sg_ready_mode(4) raises ValueError (mode out of range)."""
    with pytest.raises(ValueError, match="Invalid SG-ready mode 4"):
        translate_sg_ready_mode(4)


def test_translate_invalid_mode_negative_raises() -> None:
    """Test: translate_sg_ready_mode(-1) raises ValueError (negative mode)."""
    with pytest.raises(ValueError, match="Invalid SG-ready mode -1"):
        translate_sg_ready_mode(-1)


def test_translate_custom_mode_map() -> None:
    """Test: translate_sg_ready_mode uses custom mode_map when provided."""
    custom_map = {0: {3: 1, 4: 1}}
    result = translate_sg_ready_mode(0, mode_map=custom_map)
    assert result == {3: 1, 4: 1}


def test_translate_invalid_mode_with_custom_map_raises() -> None:
    """Test: translate_sg_ready_mode raises for mode not in custom map."""
    custom_map = {0: {3: 1, 4: 1}}
    with pytest.raises(ValueError, match="Invalid SG-ready mode 1"):
        translate_sg_ready_mode(1, mode_map=custom_map)


# ---------------------------------------------------------------------------
# validate_sg_ready_mode tests
# ---------------------------------------------------------------------------


def test_validate_valid_modes() -> None:
    """Test: validate_sg_ready_mode returns True for modes 0-3."""
    for mode in range(4):
        assert validate_sg_ready_mode(mode) is True


def test_validate_invalid_mode_4() -> None:
    """Test: validate_sg_ready_mode returns False for mode 4."""
    assert validate_sg_ready_mode(4) is False


def test_validate_negative_mode() -> None:
    """Test: validate_sg_ready_mode returns False for negative mode."""
    assert validate_sg_ready_mode(-1) is False


# ---------------------------------------------------------------------------
# SgReadyWrite dataclass tests
# ---------------------------------------------------------------------------


def test_sg_ready_write_has_mode_and_param_writes() -> None:
    """Test: SgReadyWrite stores mode and param_writes correctly."""
    write = SgReadyWrite(mode=1, param_writes={3: 0, 4: 0})
    assert write.mode == 1
    assert write.param_writes == {3: 0, 4: 0}
