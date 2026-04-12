"""Bath Boost (Badebooster) manager for Luxtronik 2.0 heat pumps.

Provides on-demand hot water heating to a configurable target temperature with
progress tracking and automatic deactivation. When activated via the button
entity, the manager:

1. Sets hot water mode to Party (forces immediate heating)
2. Raises the hot water setpoint to the target temperature
3. Monitors current hot water temperature via coordinator updates
4. Automatically restores normal mode and setpoint when target is reached

Progress tracking includes a dynamically calculated heat rate based on
observed temperature changes, providing estimated remaining time.
"""

from __future__ import annotations

import logging
from datetime import datetime

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback

from .const import (
    DEFAULT_BATH_BOOST_HEAT_RATE,
    DEFAULT_BATH_BOOST_NORMAL_TEMP,
    DEFAULT_BATH_BOOST_TARGET_TEMP,
    HOT_WATER_MODE_AUTOMATIC,
    HOT_WATER_MODE_PARTY,
    PARAM_HOT_WATER_MODE,
    PARAM_HOT_WATER_SETPOINT,
)
from .coordinator import LuxtronikCoordinator

_LOGGER = logging.getLogger(__name__)

# Luxtronik calculation index for current hot water temperature
_CALC_HOT_WATER_TEMP = 17


class BathBoostManager:
    """Manages the Bath Boost feature.

    Instantiated once per config entry in __init__.py. Listens to coordinator
    data updates to evaluate whether the target temperature has been reached
    and to calculate dynamic heat rate estimates.

    Attributes:
        coordinator: The LuxtronikCoordinator for writing parameters.
        entry: The config entry holding all settings.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        coordinator: LuxtronikCoordinator,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the bath boost manager.

        Args:
            hass: The Home Assistant instance.
            coordinator: The LuxtronikCoordinator for parameter writes.
            entry: The config entry with bath boost settings.
        """
        self.hass = hass
        self.coordinator = coordinator
        self.entry = entry

        # Boost state
        self._boost_active = False
        self._boost_activated_at: datetime | None = None
        self._start_temp: float | None = None

        # Temperature tracking for heat rate estimation
        self._last_temp: float | None = None
        self._last_temp_time: datetime | None = None
        self._observed_heat_rate: float | None = None

        # Coordinator listener unsub
        self._unsub_listener = None

    @property
    def target_temp(self) -> float:
        """Return the boost target temperature in degrees C."""
        return self.entry.data.get(
            "bath_boost_target_temp", DEFAULT_BATH_BOOST_TARGET_TEMP
        )

    @property
    def normal_temp(self) -> float:
        """Return the normal hot water temperature to restore after boost."""
        return self.entry.data.get(
            "bath_boost_normal_temp", DEFAULT_BATH_BOOST_NORMAL_TEMP
        )

    @property
    def boost_active(self) -> bool:
        """Return whether bath boost is currently active."""
        return self._boost_active

    @property
    def boost_activated_at(self) -> datetime | None:
        """Return the timestamp when boost was activated."""
        return self._boost_activated_at

    @property
    def current_temp(self) -> float | None:
        """Return the current hot water temperature from coordinator data.

        Reads calculation index 17 (ID_WEB_Temperatur_TBW) and converts
        from raw integer (tenths of degrees) to float degrees C.
        """
        raw = self.coordinator.data.get("calculations", {}).get(
            _CALC_HOT_WATER_TEMP
        )
        if raw is None:
            return None
        return raw / 10.0

    @property
    def progress_percent(self) -> float | None:
        """Return boost progress as percentage (0-100).

        Calculated as (current - start) / (target - start) * 100.
        Returns None if boost is not active or start temp is unavailable.
        """
        if not self._boost_active or self._start_temp is None:
            return None
        current = self.current_temp
        if current is None:
            return None
        total = self.target_temp - self._start_temp
        if total <= 0:
            return 100.0
        progress = (current - self._start_temp) / total * 100.0
        return max(0.0, min(100.0, progress))

    @property
    def estimated_remaining_minutes(self) -> int | None:
        """Return estimated minutes until target temperature is reached.

        Uses the observed heat rate if available (calculated from consecutive
        coordinator readings), otherwise falls back to DEFAULT_BATH_BOOST_HEAT_RATE.
        Returns None if boost is not active or target already reached.
        """
        if not self._boost_active:
            return None
        current = self.current_temp
        if current is None:
            return None
        remaining_degrees = self.target_temp - current
        if remaining_degrees <= 0:
            return 0
        rate = self._observed_heat_rate or DEFAULT_BATH_BOOST_HEAT_RATE
        if rate <= 0:
            return None
        return max(1, int(remaining_degrees / rate * 60))

    async def async_activate(self) -> None:
        """Activate bath boost — set Party mode and raise setpoint.

        Sets hot water mode to Party (raw 2) to force immediate heating,
        and raises the setpoint to the target temperature. Both parameters
        are written atomically via the coordinator.
        """
        if self._boost_active:
            _LOGGER.debug("Bath boost already active — ignoring duplicate activation")
            return

        current = self.current_temp
        _LOGGER.info(
            "Bath boost ACTIVATING — target %.1f°C (current: %s°C)",
            self.target_temp,
            f"{current:.1f}" if current is not None else "unknown",
        )

        self._boost_active = True
        self._boost_activated_at = datetime.now()
        self._start_temp = current
        self._last_temp = current
        self._last_temp_time = datetime.now()
        self._observed_heat_rate = None

        await self.coordinator.async_write_parameters(
            {
                PARAM_HOT_WATER_MODE: HOT_WATER_MODE_PARTY,
                PARAM_HOT_WATER_SETPOINT: int(self.target_temp * 10),
            }
        )

    async def async_deactivate(self) -> None:
        """Deactivate bath boost — restore Automatic mode and normal setpoint."""
        _LOGGER.info(
            "Bath boost DEACTIVATING — restoring normal temp %.1f°C",
            self.normal_temp,
        )

        self._boost_active = False
        self._boost_activated_at = None
        self._start_temp = None
        self._last_temp = None
        self._last_temp_time = None
        self._observed_heat_rate = None

        await self.coordinator.async_write_parameters(
            {
                PARAM_HOT_WATER_MODE: HOT_WATER_MODE_AUTOMATIC,
                PARAM_HOT_WATER_SETPOINT: int(self.normal_temp * 10),
            }
        )

    async def async_evaluate(self) -> None:
        """Evaluate bath boost state on coordinator data update.

        Called each time the coordinator refreshes data. Updates the observed
        heat rate and checks if the target temperature has been reached.
        """
        if not self._boost_active:
            return

        current = self.current_temp
        if current is None:
            return

        now = datetime.now()

        # Update observed heat rate from consecutive readings
        if self._last_temp is not None and self._last_temp_time is not None:
            elapsed_hours = (now - self._last_temp_time).total_seconds() / 3600
            if elapsed_hours > 0:
                rate = (current - self._last_temp) / elapsed_hours
                # Only update if temperature is rising (positive rate)
                if rate > 0:
                    self._observed_heat_rate = rate

        self._last_temp = current
        self._last_temp_time = now

        # Check if target reached
        if current >= self.target_temp:
            _LOGGER.info(
                "Bath boost target reached — current %.1f°C >= target %.1f°C",
                current,
                self.target_temp,
            )
            await self.async_deactivate()

    async def async_start(self) -> None:
        """Start listening to coordinator updates.

        Called from __init__.py after the coordinator is set up.
        """
        self._unsub_listener = self.coordinator.async_add_listener(
            self._on_coordinator_update
        )
        _LOGGER.info("Bath boost manager started")

    async def async_stop(self) -> None:
        """Stop listening and restore normal parameters if boost is active."""
        if self._unsub_listener:
            self._unsub_listener()
            self._unsub_listener = None

        if self._boost_active:
            await self.async_deactivate()

    @callback
    def _on_coordinator_update(self) -> None:
        """Handle coordinator data update."""
        self.hass.async_create_task(self.async_evaluate())
