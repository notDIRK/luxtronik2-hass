"""Integration tests for luxtronik2-modbus-proxy using a mock Luxtronik client.

Tests the full proxy stack in-process by replacing the LuxtronikClient with a
MockLuxtronikClient that returns predetermined values. Uses pymodbus AsyncModbusTcpClient
to connect to the proxy's Modbus server on test port 15502 (avoids requiring root).

Test coverage:
- Read holding register (FC3): HeatingMode at address 3
- Read input register (FC4): flow temperature at address 10
- Write valid value (FC6): HeatingMode=2 (Party) at address 3
- Write invalid value (FC6): value 99 to HeatingMode address 3 -> Modbus exception code 3
"""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock

import pytest
from pymodbus.client import AsyncModbusTcpClient
from pymodbus.exceptions import ModbusException

from luxtronik2_modbus_proxy.config import ProxyConfig
from luxtronik2_modbus_proxy.luxtronik_client import LuxtronikClient
from luxtronik2_modbus_proxy.modbus_server import build_modbus_server
from luxtronik2_modbus_proxy.register_cache import RegisterCache
from luxtronik2_modbus_proxy.register_map import RegisterMap

# Test port: must be above 1024 to avoid requiring root privileges.
TEST_MODBUS_PORT: int = 15502

# Predetermined mock values for testing.
# HeatingMode=2 (Party), stored at holding register address 3.
MOCK_HEATING_MODE: int = 2
# Flow temperature=215 (21.5 C raw), stored at input register address 10.
MOCK_FLOW_TEMP: int = 215


class MockLuxtronikClient(LuxtronikClient):
    """Mock replacement for LuxtronikClient that returns predetermined values.

    Overrides async_read to return a sentinel (no network call) and
    update_cache_from_read to populate the cache with fixed test values.
    Also records write calls for assertion in write tests.

    Attributes:
        received_writes: List of param_writes dicts from async_write calls.
    """

    def __init__(self, register_map: RegisterMap) -> None:
        """Initialize the mock client without real network parameters.

        Args:
            register_map: Register map used by update_cache_from_read to enumerate addresses.
        """
        # Use placeholder host/port — no real network calls are made.
        super().__init__(host="192.168.x.x", port=8889, register_map=register_map)
        self.received_writes: list[dict[int, int]] = []

    async def async_read(self) -> Any:
        """Return a sentinel object — no network call is made.

        Returns:
            None sentinel; update_cache_from_read ignores this argument
            and uses predetermined values instead.
        """
        return None

    async def async_write(self, param_writes: dict[int, int]) -> None:
        """Record write calls for test assertion without making network calls.

        Args:
            param_writes: Mapping of parameter index to raw integer value.
        """
        self.received_writes.append(param_writes)

    def update_cache_from_read(self, lux: Any, cache: RegisterCache) -> None:
        """Populate the register cache with predetermined test values.

        Bypasses the luxtronik library entirely and directly updates the cache
        with known values for test assertions.

        Args:
            lux: Ignored sentinel (mock does not use a real Luxtronik instance).
            cache: Register cache to populate with test values.
        """
        # Write HeatingMode=2 (Party) to holding register address 3.
        cache.update_holding_values(3, [MOCK_HEATING_MODE])
        # Write flow temperature=215 (21.5 C raw) to input register address 10.
        cache.update_input_values(10, [MOCK_FLOW_TEMP])


@pytest.fixture
async def proxy_stack():
    """Start the full proxy stack with a mock Luxtronik client.

    Creates all proxy components in dependency order, runs one manual poll cycle
    to populate the cache with mock values, and starts the Modbus server on
    TEST_MODBUS_PORT. Yields a dict with all components for test access.
    Tears down the server after each test.

    Yields:
        Dict with keys: config, register_map, cache, mock_client, server, server_task.
    """
    # Create config with writes enabled so write tests work.
    # Use write_rate_limit=0 so writes are never rate-limited in tests.
    config = ProxyConfig(
        luxtronik_host="192.168.x.x",
        modbus_port=TEST_MODBUS_PORT,
        bind_address="127.0.0.1",
        poll_interval=10,
        enable_writes=True,
        write_rate_limit=10,
    )

    register_map = RegisterMap()
    write_queue: asyncio.Queue = asyncio.Queue()
    cache = RegisterCache(register_map, write_queue, config.enable_writes)
    mock_client = MockLuxtronikClient(register_map)

    # Run one manual poll cycle to populate the cache before tests query it.
    # This mimics what PollingEngine._poll_cycle does without the sleep.
    lux = await mock_client.async_read()
    mock_client.update_cache_from_read(lux, cache)
    cache.mark_fresh()

    server = build_modbus_server(cache, config)

    # Start the server as a background task.
    server_task = asyncio.create_task(server.serve_forever(), name="test_modbus_server")

    # Brief delay to allow the server to start accepting connections.
    await asyncio.sleep(0.1)

    yield {
        "config": config,
        "register_map": register_map,
        "cache": cache,
        "mock_client": mock_client,
        "write_queue": write_queue,
        "server": server,
        "server_task": server_task,
    }

    # Teardown: stop the server and cancel the task.
    await server.shutdown()
    server_task.cancel()
    try:
        await server_task
    except asyncio.CancelledError:
        pass


async def test_read_holding_register(proxy_stack):
    """Read HeatingMode from holding register 3 via FC3 and verify mock value.

    The mock client populated holding register 3 with MOCK_HEATING_MODE (2).
    A Modbus client should be able to read this value back via FC3.
    """
    client = AsyncModbusTcpClient("127.0.0.1", port=TEST_MODBUS_PORT)
    await client.connect()
    assert client.connected, "Could not connect to test Modbus server"

    try:
        result = await client.read_holding_registers(address=3, count=1)
        assert not result.isError(), f"FC3 read failed: {result}"
        assert result.registers[0] == MOCK_HEATING_MODE, (
            f"Expected HeatingMode={MOCK_HEATING_MODE}, got {result.registers[0]}"
        )
    finally:
        client.close()


async def test_read_input_register(proxy_stack):
    """Read flow temperature from input register 10 via FC4 and verify mock value.

    The mock client populated input register 10 with MOCK_FLOW_TEMP (215 = 21.5 C raw).
    A Modbus client should be able to read this value back via FC4.
    """
    client = AsyncModbusTcpClient("127.0.0.1", port=TEST_MODBUS_PORT)
    await client.connect()
    assert client.connected, "Could not connect to test Modbus server"

    try:
        result = await client.read_input_registers(address=10, count=1)
        assert not result.isError(), f"FC4 read failed: {result}"
        assert result.registers[0] == MOCK_FLOW_TEMP, (
            f"Expected flow temp={MOCK_FLOW_TEMP}, got {result.registers[0]}"
        )
    finally:
        client.close()


async def test_write_valid_value(proxy_stack):
    """Write HeatingMode=2 (Party) to holding register 3 via FC6.

    With enable_writes=True and value 2 in the allowed_values list [0,1,2,3,4],
    the write should succeed (no error response) and the value should appear
    in the write queue for the polling engine to forward.
    """
    stack = proxy_stack
    write_queue = stack["write_queue"]

    client = AsyncModbusTcpClient("127.0.0.1", port=TEST_MODBUS_PORT)
    await client.connect()
    assert client.connected, "Could not connect to test Modbus server"

    try:
        result = await client.write_register(address=3, value=2)
        assert not result.isError(), (
            f"FC6 write of valid value 2 to register 3 should succeed, got: {result}"
        )
    finally:
        client.close()

    # Verify the write was enqueued for upstream delivery.
    # The ProxyHoldingDataBlock should have placed (wire_address=3, values=[2]) in the queue.
    assert not write_queue.empty(), "Write queue should contain the accepted write"
    wire_address, values = write_queue.get_nowait()
    assert wire_address == 3, f"Expected wire_address=3, got {wire_address}"
    assert values == [2], f"Expected values=[2], got {values}"


async def test_write_invalid_value(proxy_stack):
    """Write invalid value 99 to HeatingMode register 3 via FC6.

    HeatingMode only allows values [0, 1, 2, 3, 4]. Value 99 is out of range.
    The proxy should reject this write with a Modbus exception (illegal data value).
    The write queue should remain empty (no write forwarded).
    """
    stack = proxy_stack
    write_queue = stack["write_queue"]

    client = AsyncModbusTcpClient("127.0.0.1", port=TEST_MODBUS_PORT)
    await client.connect()
    assert client.connected, "Could not connect to test Modbus server"

    try:
        result = await client.write_register(address=3, value=99)
        # The result should be a Modbus exception response.
        assert result.isError(), (
            "FC6 write of invalid value 99 to register 3 should be rejected"
        )
    finally:
        client.close()

    # Verify nothing was enqueued (invalid write should not reach the controller).
    assert write_queue.empty(), "Write queue should be empty after rejected write"
