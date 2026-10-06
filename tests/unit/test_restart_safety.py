"""Unit tests for restart safety of Solar Boost, Night Heating Pause and Bath Boost.

Background (reported 2026-10-06): Boost and pause state lived only in memory.
A Home Assistant restart during an active Solar Boost left the hot water
setpoint at the boost temperature (65 °C) until the next real boost cycle,
causing compressor starts on grid power overnight. HA does not unload config
entries on shutdown, so ``async_stop`` never ran.

The fix has two parts, both covered here:
- On startup each manager reconciles with the values on the controller and
  takes over / ends a stale boost or pause.
- ``async_setup_entry`` registers an EVENT_HOMEASSISTANT_STOP listener that
  stops both managers (restoring normal values) when HA shuts down.

The managers are tested against a mocked hass/coordinator; no HA runtime needed.
"""

from __future__ import annotations

from datetime import datetime as real_datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import custom_components.luxtronik2_hass as integration
from custom_components.luxtronik2_hass import smart_energy as se_module
from custom_components.luxtronik2_hass.bath_boost import BathBoostManager
from custom_components.luxtronik2_hass.const import (
    HEATING_MODE_AUTO,
    HEATING_MODE_OFF,
    HOT_WATER_MODE_AUTOMATIC,
    HOT_WATER_MODE_PARTY,
    PARAM_HEATING_MODE,
    PARAM_HOT_WATER_MODE,
    PARAM_HOT_WATER_SETPOINT,
)
from custom_components.luxtronik2_hass.smart_energy import SmartEnergyManager

GRID = "sensor.grid_total"

# Dirk's production config at the time of the report
SOLAR_CONFIG = {
    "solar_boost_enabled": True,
    "grid_sensor": GRID,
    "solar_threshold": 1500,
    "solar_normal_temp": 55.5,
    "solar_boost_temp": 65.0,
    "solar_min_runtime": 30,
    "night_pause_enabled": False,
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _hass(grid_power: str | None = None) -> MagicMock:
    """Return a mocked hass whose grid sensor reports ``grid_power`` watts."""
    hass = MagicMock()
    hass.states.get.return_value = (
        SimpleNamespace(state=grid_power) if grid_power is not None else None
    )
    return hass


def _coordinator(params: dict[int, int]) -> MagicMock:
    """Return a mocked coordinator holding the given controller parameters."""
    coordinator = MagicMock()
    coordinator.data = {"parameters": dict(params), "calculations": {17: 480}}
    coordinator.async_write_parameter = AsyncMock()
    coordinator.async_write_parameters = AsyncMock()
    return coordinator


def _entry(**data) -> SimpleNamespace:
    return SimpleNamespace(entry_id="abc", data=data)


def _at(hour: int, minute: int = 0):
    """Patch smart_energy.datetime so that now() returns today at hour:minute."""

    class _FixedDatetime(real_datetime):
        @classmethod
        def now(cls, tz=None):
            return real_datetime(2026, 10, 7, hour, minute)

    return patch.object(se_module, "datetime", _FixedDatetime)


async def _start_smart_energy(hass, coordinator, entry) -> SmartEnergyManager:
    manager = SmartEnergyManager(hass, coordinator, entry)
    with patch.object(se_module, "async_track_state_change_event"), patch.object(
        se_module, "async_track_time_interval"
    ):
        await manager.async_start()
    return manager


# ---------------------------------------------------------------------------
# Solar Boost
# ---------------------------------------------------------------------------


async def test_stale_solar_boost_is_reset_on_startup_without_surplus():
    """The reported bug: setpoint stuck at 65 °C after restart, no surplus."""
    coordinator = _coordinator({PARAM_HOT_WATER_SETPOINT: 650})
    with _at(22):
        manager = await _start_smart_energy(
            _hass("400"), coordinator, _entry(**SOLAR_CONFIG)
        )

    coordinator.async_write_parameter.assert_awaited_once_with(
        PARAM_HOT_WATER_SETPOINT, 555
    )
    assert manager.boost_active is False


async def test_stale_solar_boost_is_kept_while_surplus_continues():
    """Restart during real surplus: boost is taken over, nothing is written."""
    coordinator = _coordinator({PARAM_HOT_WATER_SETPOINT: 650})
    with _at(13):
        manager = await _start_smart_energy(
            _hass("-2500"), coordinator, _entry(**SOLAR_CONFIG)
        )

    coordinator.async_write_parameter.assert_not_awaited()
    assert manager.boost_active is True


async def test_stale_solar_boost_waits_for_unavailable_grid_sensor():
    """Grid sensor not ready yet: boost is adopted, ended on the first value."""
    coordinator = _coordinator({PARAM_HOT_WATER_SETPOINT: 650})
    hass = _hass("unavailable")
    with _at(22):
        manager = await _start_smart_energy(hass, coordinator, _entry(**SOLAR_CONFIG))
        coordinator.async_write_parameter.assert_not_awaited()
        assert manager.boost_active is True

        hass.states.get.return_value = SimpleNamespace(state="300")
        await manager._evaluate_solar_boost()

    coordinator.async_write_parameter.assert_awaited_once_with(
        PARAM_HOT_WATER_SETPOINT, 555
    )


@pytest.mark.parametrize(
    ("params", "config_changes"),
    [
        # Setpoint already normal
        ({PARAM_HOT_WATER_SETPOINT: 555}, {}),
        # Manual setpoint that differs from the boost value
        ({PARAM_HOT_WATER_SETPOINT: 600}, {}),
        # Solar Boost disabled: a 65 °C setpoint is the user's own choice
        ({PARAM_HOT_WATER_SETPOINT: 650}, {"solar_boost_enabled": False}),
        # Party mode: Bath Boost owns the setpoint
        (
            {PARAM_HOT_WATER_SETPOINT: 650, PARAM_HOT_WATER_MODE: HOT_WATER_MODE_PARTY},
            {},
        ),
    ],
)
async def test_solar_boost_startup_leaves_other_setpoints_alone(params, config_changes):
    """Only the exact boost value, with Solar Boost enabled, is taken over."""
    coordinator = _coordinator(params)
    with _at(22):
        manager = await _start_smart_energy(
            _hass("400"), coordinator, _entry(**{**SOLAR_CONFIG, **config_changes})
        )

    coordinator.async_write_parameter.assert_not_awaited()
    assert manager.boost_active is False


# ---------------------------------------------------------------------------
# Night Heating Pause
# ---------------------------------------------------------------------------

NIGHT_CONFIG = {
    "solar_boost_enabled": False,
    "night_pause_enabled": True,
    "night_pause_start": "18:00",
    "night_pause_end": "09:00",
}


async def test_stale_night_pause_is_ended_after_window():
    """HA was down when the pause window ended: heating must not stay OFF."""
    coordinator = _coordinator({PARAM_HEATING_MODE: HEATING_MODE_OFF})
    with _at(10):
        manager = await _start_smart_energy(
            _hass(), coordinator, _entry(**NIGHT_CONFIG)
        )

    coordinator.async_write_parameter.assert_awaited_once_with(
        PARAM_HEATING_MODE, HEATING_MODE_AUTO
    )
    assert manager.night_pause_currently_active is False


async def test_night_pause_inside_window_is_taken_over_without_write():
    """Restart inside the window: pause continues and ends normally later."""
    coordinator = _coordinator({PARAM_HEATING_MODE: HEATING_MODE_OFF})
    with _at(23):
        manager = await _start_smart_energy(
            _hass(), coordinator, _entry(**NIGHT_CONFIG)
        )

    coordinator.async_write_parameter.assert_not_awaited()
    assert manager.night_pause_currently_active is True


async def test_heating_off_is_left_alone_when_night_pause_disabled():
    """Heating OFF in summer is a manual setting, not a stale pause."""
    coordinator = _coordinator({PARAM_HEATING_MODE: HEATING_MODE_OFF})
    with _at(10):
        await _start_smart_energy(
            _hass(), coordinator, _entry(**{**NIGHT_CONFIG, "night_pause_enabled": False})
        )

    coordinator.async_write_parameter.assert_not_awaited()


async def test_smart_energy_stop_restores_once():
    """async_stop runs on HA stop and again on unload; second call is a no-op."""
    coordinator = _coordinator({PARAM_HOT_WATER_SETPOINT: 650})
    with _at(13):
        manager = await _start_smart_energy(
            _hass("-2500"), coordinator, _entry(**SOLAR_CONFIG)
        )
        await manager.async_stop()
        await manager.async_stop()

    coordinator.async_write_parameter.assert_awaited_once_with(
        PARAM_HOT_WATER_SETPOINT, 555
    )


# ---------------------------------------------------------------------------
# Bath Boost
# ---------------------------------------------------------------------------

BATH_CONFIG = {"bath_boost_target_temp": 65.0, "bath_boost_normal_temp": 55.5}


async def test_stale_bath_boost_is_reset_on_startup():
    """Party mode at the bath target after a crash is reset to normal."""
    coordinator = _coordinator(
        {PARAM_HOT_WATER_MODE: HOT_WATER_MODE_PARTY, PARAM_HOT_WATER_SETPOINT: 650}
    )
    manager = BathBoostManager(MagicMock(), coordinator, _entry(**BATH_CONFIG))
    await manager.async_start()

    coordinator.async_write_parameters.assert_awaited_once_with(
        {PARAM_HOT_WATER_MODE: HOT_WATER_MODE_AUTOMATIC, PARAM_HOT_WATER_SETPOINT: 555}
    )
    assert manager.boost_active is False


@pytest.mark.parametrize(
    "params",
    [
        # Manual Party mode with a different setpoint
        {PARAM_HOT_WATER_MODE: HOT_WATER_MODE_PARTY, PARAM_HOT_WATER_SETPOINT: 600},
        # 65 °C in Automatic mode (e.g. Solar Boost) is not a bath boost
        {PARAM_HOT_WATER_MODE: HOT_WATER_MODE_AUTOMATIC, PARAM_HOT_WATER_SETPOINT: 650},
    ],
)
async def test_bath_boost_startup_leaves_other_states_alone(params):
    """Only the exact Party + target pair counts as a stale bath boost."""
    coordinator = _coordinator(params)
    manager = BathBoostManager(MagicMock(), coordinator, _entry(**BATH_CONFIG))
    await manager.async_start()

    coordinator.async_write_parameters.assert_not_awaited()


async def test_bath_boost_reset_failure_does_not_break_setup():
    """An unreachable controller during cleanup must not fail entry setup."""
    coordinator = _coordinator(
        {PARAM_HOT_WATER_MODE: HOT_WATER_MODE_PARTY, PARAM_HOT_WATER_SETPOINT: 650}
    )
    coordinator.async_write_parameters.side_effect = OSError("controller offline")
    manager = BathBoostManager(MagicMock(), coordinator, _entry(**BATH_CONFIG))

    await manager.async_start()  # must not raise

    coordinator.async_add_listener.assert_called_once()


# ---------------------------------------------------------------------------
# Shutdown wiring in async_setup_entry
# ---------------------------------------------------------------------------


async def test_setup_entry_stops_managers_on_ha_shutdown():
    """HA shutdown stops both managers, even if one of them fails."""
    hass = MagicMock()
    hass.data = {}
    hass.config_entries.async_forward_entry_setups = AsyncMock()
    entry = MagicMock()
    entry.entry_id = "abc"
    entry.data = {"host": "192.0.2.10"}

    started: list[str] = []
    bath = MagicMock(async_start=AsyncMock(side_effect=lambda: started.append("bath")),
                     async_stop=AsyncMock())
    smart = MagicMock(async_start=AsyncMock(side_effect=lambda: started.append("smart")),
                      async_stop=AsyncMock(side_effect=OSError("controller offline")))

    coordinator = MagicMock(async_config_entry_first_refresh=AsyncMock())
    with patch.object(integration, "LuxtronikCoordinator", return_value=coordinator), \
         patch.object(integration, "BathBoostManager", return_value=bath), \
         patch.object(integration, "SmartEnergyManager", return_value=smart):
        assert await integration.async_setup_entry(hass, entry)

    # Bath Boost must clean up before Smart Energy reconciles
    assert started == ["bath", "smart"]

    event_type, handler = hass.bus.async_listen_once.call_args.args
    assert event_type == integration.EVENT_HOMEASSISTANT_STOP

    # A failing manager must not keep the other from restoring its values
    await handler(MagicMock())
    bath.async_stop.assert_awaited_once()
    smart.async_stop.assert_awaited_once()
