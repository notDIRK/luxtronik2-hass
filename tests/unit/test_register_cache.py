"""Unit tests for register_cache module.

Tests cover ProxyHoldingDataBlock write validation (write gating, value validation,
non-writable address rejection, enable_writes guard) and RegisterCache initialization
and update methods (wire-address-aware setValues, stale/fresh state transitions).
"""

from __future__ import annotations

import asyncio

import pytest

from luxtronik2_modbus_proxy.register_cache import ProxyHoldingDataBlock, RegisterCache
from luxtronik2_modbus_proxy.register_map import RegisterMap


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def register_map() -> RegisterMap:
    """Return a default RegisterMap with the curated register set."""
    return RegisterMap()


@pytest.fixture()
def write_queue() -> asyncio.Queue:
    """Return a fresh async write queue."""
    return asyncio.Queue()


@pytest.fixture()
def cache(register_map: RegisterMap, write_queue: asyncio.Queue) -> RegisterCache:
    """Return a RegisterCache with enable_writes=True for write path tests."""
    return RegisterCache(register_map=register_map, write_queue=write_queue, enable_writes=True)


# ---------------------------------------------------------------------------
# ProxyHoldingDataBlock tests
# ---------------------------------------------------------------------------


async def test_valid_write_updates_cache_and_queues(
    cache: RegisterCache, write_queue: asyncio.Queue
) -> None:
    """Test 1: Valid HeatingMode write updates cache and puts item on queue.

    HeatingMode is at wire address 3 (datablock address 4 = wire + 1).
    Allowed values: 0, 1, 2, 3, 4 (from parameters.py HeatingMode enum).
    """
    result = await cache.holding_datablock.async_setValues(address=4, values=[2])
    assert result is None, "Valid write should return None (success)"
    assert write_queue.qsize() == 1
    wire_addr, values = write_queue.get_nowait()
    assert wire_addr == 3, "Wire address should be datablock_address - 1"
    assert values == [2]


async def test_invalid_write_value_rejected(
    cache: RegisterCache, write_queue: asyncio.Queue
) -> None:
    """Test 2: Invalid HeatingMode value 99 returns ILLEGAL_VALUE, nothing queued."""
    from pymodbus.datastore.sequential import ExcCodes

    result = await cache.holding_datablock.async_setValues(address=4, values=[99])
    assert result == ExcCodes.ILLEGAL_VALUE
    assert write_queue.qsize() == 0, "Invalid write must not enqueue"


async def test_non_writable_address_rejected(
    cache: RegisterCache, write_queue: asyncio.Queue
) -> None:
    """Test 3: Write to non-writable address returns ILLEGAL_VALUE.

    Input register addresses are not in holding map; address 50 (wire 49) is unmapped.
    """
    from pymodbus.datastore.sequential import ExcCodes

    result = await cache.holding_datablock.async_setValues(address=50, values=[1])
    assert result == ExcCodes.ILLEGAL_VALUE
    assert write_queue.qsize() == 0


async def test_writes_disabled_returns_illegal_value(
    register_map: RegisterMap, write_queue: asyncio.Queue
) -> None:
    """Test 4: When enable_writes=False, all writes return ILLEGAL_VALUE regardless of address."""
    from pymodbus.datastore.sequential import ExcCodes

    cache_no_writes = RegisterCache(
        register_map=register_map, write_queue=write_queue, enable_writes=False
    )
    result = await cache_no_writes.holding_datablock.async_setValues(address=4, values=[2])
    assert result == ExcCodes.ILLEGAL_VALUE
    assert write_queue.qsize() == 0


# ---------------------------------------------------------------------------
# RegisterCache.update_holding_values tests
# ---------------------------------------------------------------------------


def test_update_holding_values_stores_value(cache: RegisterCache) -> None:
    """Test 5: update_holding_values(3, [2]) stores value retrievable at datablock address 4."""
    cache.update_holding_values(3, [2])
    retrieved = cache.holding_datablock.getValues(4, 1)
    assert retrieved == [2], "update_holding_values stores at wire_address + 1"


def test_update_input_values_stores_value(cache: RegisterCache) -> None:
    """Test 6: update_input_values(10, [225]) stores value retrievable at datablock address 11."""
    cache.update_input_values(10, [225])
    retrieved = cache.input_datablock.getValues(11, 1)
    assert retrieved == [225], "update_input_values stores at wire_address + 1"


# ---------------------------------------------------------------------------
# RegisterCache initialization tests
# ---------------------------------------------------------------------------


def test_holding_datablock_size(register_map: RegisterMap, write_queue: asyncio.Queue) -> None:
    """Test 7: holding_datablock initialized with address=1 and size 5001 (HOLDING_BLOCK_SIZE).

    Size increased from 1200 to 5001 in Phase 2 to accommodate the SG-ready virtual
    register at address 5000 (Plan 03).
    """
    cache = RegisterCache(
        register_map=register_map, write_queue=write_queue, enable_writes=False
    )
    block = cache.holding_datablock
    assert block.address == 1
    assert len(block.values) == 5001


def test_input_datablock_size(register_map: RegisterMap, write_queue: asyncio.Queue) -> None:
    """Test 8: input_datablock initialized with address=1 and size 1355 (INPUT_BLOCK_SIZE).

    Size increased from 260 to 1355 in Phase 2 to cover visibility registers at 1000-1354.
    """
    cache = RegisterCache(
        register_map=register_map, write_queue=write_queue, enable_writes=False
    )
    block = cache.input_datablock
    assert block.address == 1
    assert len(block.values) == 1355


# ---------------------------------------------------------------------------
# RegisterCache stale/fresh state tests
# ---------------------------------------------------------------------------


def test_mark_stale(cache: RegisterCache) -> None:
    """Test 9: mark_stale() sets is_stale=True."""
    cache.mark_fresh()  # set fresh first so we can verify the transition
    cache.mark_stale()
    assert cache.is_stale is True


def test_mark_fresh(cache: RegisterCache) -> None:
    """Test 10: mark_fresh() sets is_stale=False and updates last_successful_read."""
    assert cache.is_stale is True  # cache starts stale
    cache.mark_fresh()
    assert cache.is_stale is False
    assert cache.last_successful_read is not None


# ---------------------------------------------------------------------------
# SG-ready virtual register interception tests (Plan 03)
# ---------------------------------------------------------------------------


async def test_sg_ready_write_enqueues_sg_ready_write(
    cache: RegisterCache, write_queue: asyncio.Queue
) -> None:
    """Test 11: Write to datablock address 5001 (wire 5000) enqueues SgReadyWrite.

    The SG-ready register is at wire address 5000, datablock address 5001.
    A valid mode write (0-3) should enqueue an SgReadyWrite (not a raw tuple).
    """
    from luxtronik2_modbus_proxy.sg_ready import SgReadyWrite

    result = await cache.holding_datablock.async_setValues(address=5001, values=[1])
    assert result is None, "Valid SG-ready write should return None (success)"
    assert write_queue.qsize() == 1
    item = write_queue.get_nowait()
    assert isinstance(item, SgReadyWrite), "SG-ready write must enqueue SgReadyWrite"
    assert item.mode == 1
    assert item.param_writes == {3: 0, 4: 0}


async def test_sg_ready_invalid_mode_rejected(
    cache: RegisterCache, write_queue: asyncio.Queue
) -> None:
    """Test 12: Write mode 5 to datablock address 5001 returns ILLEGAL_VALUE.

    Mode 5 is outside the valid SG-ready range (0-3) and must be rejected
    before reaching the write queue.
    """
    from pymodbus.datastore.sequential import ExcCodes

    result = await cache.holding_datablock.async_setValues(address=5001, values=[5])
    assert result == ExcCodes.ILLEGAL_VALUE
    assert write_queue.qsize() == 0, "Invalid SG-ready mode must not enqueue"


async def test_sg_ready_write_disabled_returns_illegal_value(
    register_map: RegisterMap, write_queue: asyncio.Queue
) -> None:
    """Test 13: With enable_writes=False, SG-ready write returns ILLEGAL_VALUE.

    The global enable_writes guard takes priority over SG-ready interception.
    """
    from pymodbus.datastore.sequential import ExcCodes

    cache_no_writes = RegisterCache(
        register_map=register_map, write_queue=write_queue, enable_writes=False
    )
    result = await cache_no_writes.holding_datablock.async_setValues(
        address=5001, values=[1]
    )
    assert result == ExcCodes.ILLEGAL_VALUE
    assert write_queue.qsize() == 0


async def test_sg_ready_mode_0_maps_to_evu_lock(
    cache: RegisterCache, write_queue: asyncio.Queue
) -> None:
    """Test 14: SG-ready mode 0 enqueues EVU lock parameter writes {3:4, 4:4}."""
    from luxtronik2_modbus_proxy.sg_ready import SgReadyWrite

    await cache.holding_datablock.async_setValues(address=5001, values=[0])
    item = write_queue.get_nowait()
    assert isinstance(item, SgReadyWrite)
    assert item.mode == 0
    assert item.param_writes == {3: 4, 4: 4}


async def test_sg_ready_mode_3_maps_to_force_on(
    cache: RegisterCache, write_queue: asyncio.Queue
) -> None:
    """Test 15: SG-ready mode 3 enqueues Force on parameter writes {3:0, 4:2}."""
    from luxtronik2_modbus_proxy.sg_ready import SgReadyWrite

    await cache.holding_datablock.async_setValues(address=5001, values=[3])
    item = write_queue.get_nowait()
    assert isinstance(item, SgReadyWrite)
    assert item.mode == 3
    assert item.param_writes == {3: 0, 4: 2}
