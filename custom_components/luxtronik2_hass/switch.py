"""Switch platform for Luxtronik 2.0 Smart Energy features.

Provides toggle switches for independently enabling/disabling:
- Solar Boost: raises hot water setpoint when grid feed-in exceeds threshold
- Night Heating Pause: disables floor heating during night hours

Both features are designed for heat pumps with multi-layer buffer tanks and
domestic hot water (DHW) heat exchangers. See smart_energy.py for the logic.
"""

from __future__ import annotations

import logging

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .const import (
    DEFAULT_NIGHT_PAUSE_ENABLED,
    DEFAULT_SOLAR_BOOST_ENABLED,
    DOMAIN,
    MANUFACTURER,
    MODEL,
)

_LOGGER = logging.getLogger(__name__)


class LuxtronikSmartEnergySwitch(SwitchEntity, RestoreEntity):
    """Base switch for Smart Energy features.

    Stores the toggle state in config entry data so it persists across
    restarts. Inherits from RestoreEntity so that ``last_changed`` and
    ``last_updated`` timestamps survive HA restarts — the user sees when
    the switch was actually toggled, not when HA last started.
    """

    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        key: str,
        default: bool,
    ) -> None:
        """Initialize the switch.

        Args:
            hass: The Home Assistant instance.
            entry: The config entry holding the setting.
            key: The config entry data key (e.g. "solar_boost_enabled").
            default: The default value if the key is not set.
        """
        self.hass = hass
        self._entry = entry
        self._key = key
        self._default = default
        self._attr_unique_id = f"{entry.entry_id}_switch_{key}"
        self._attr_translation_key = key

    async def async_added_to_hass(self) -> None:
        """Restore previous state on startup to preserve last_changed timestamp."""
        await super().async_added_to_hass()
        last_state = await self.async_get_last_state()
        # State is authoritative from config entry data, but restoring
        # prevents HA from treating startup as a state change event.
        if last_state is not None:
            self._attr_is_on = last_state.state == "on"

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info for grouping under the heat pump device."""
        return DeviceInfo(
            identifiers={(DOMAIN, self._entry.entry_id)},
            name=MODEL,
            manufacturer=MANUFACTURER,
            model=MODEL,
        )

    @property
    def is_on(self) -> bool:
        """Return whether the feature is enabled."""
        return self._entry.data.get(self._key, self._default)

    async def async_turn_on(self, **kwargs) -> None:
        """Enable the feature."""
        await self._update_setting(True)

    async def async_turn_off(self, **kwargs) -> None:
        """Disable the feature."""
        await self._update_setting(False)

    async def _update_setting(self, value: bool) -> None:
        """Write the setting to config entry data and reload."""
        new_data = {**self._entry.data, self._key: value}
        self.hass.config_entries.async_update_entry(self._entry, data=new_data)
        self.async_write_ha_state()


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Smart Energy switch entities from a config entry.

    Args:
        hass: The Home Assistant instance.
        entry: The config entry to set up.
        async_add_entities: Callback to register entity objects with HA.
    """
    entities = [
        LuxtronikSmartEnergySwitch(
            hass, entry, "solar_boost_enabled", DEFAULT_SOLAR_BOOST_ENABLED
        ),
        LuxtronikSmartEnergySwitch(
            hass, entry, "night_pause_enabled", DEFAULT_NIGHT_PAUSE_ENABLED
        ),
    ]
    _LOGGER.debug("Registered %d smart energy switch entities", len(entities))
    async_add_entities(entities)
