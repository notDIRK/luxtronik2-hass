"""Select platform for the Luxtronik 2 Modbus Proxy Home Assistant integration.

Provides select entities for controlling heat pump operating modes:

- HeatingMode (parameter 3, ID_Ba_Hz): Automatic, Second heatsource, Party, Holidays, Off (CTRL-01)
- HotWaterMode (parameter 4, ID_Ba_Bw): Same options as HeatingMode (CTRL-01)
- SG-Ready (virtual): Off/Blocking/Standard/Boost modes, each writing a combination
  of parameters 3 and 4 atomically (CTRL-02)

All writes route through coordinator.async_write_parameter[s]() which enforces
the single-connection constraint (ARCH-03) and NAND flash rate limiting (CTRL-04).

Entity names and option labels are localized via translation_key + strings.json.
The options list contains translation keys (not display strings) — HA renders
localized labels from the entity.select.<key>.state section of strings.json.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from homeassistant.components.select import SelectEntity, SelectEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER, MODEL
from .coordinator import LuxtronikCoordinator

_LOGGER = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Value maps
# ---------------------------------------------------------------------------

# HeatingMode and HotWaterMode share the same code-to-option mapping.
# Keys: raw integer from Luxtronik parameter. Values: translation keys matching
# strings.json entity.select.heating_mode.state / hot_water_mode.state keys.
# Verified via Python introspection of luxtronik.datatypes HeatingMode.codes (D-07, D-23).
MODE_OPTIONS: dict[int, str] = {
    0: "automatic",
    1: "second_heatsource",
    2: "party",
    3: "holidays",
    4: "off",
}
MODE_REVERSE: dict[str, int] = {v: k for k, v in MODE_OPTIONS.items()}

# SG-Ready mode labels as translation keys (D-10).
# Maps SG-Ready mode integer (0-3) to the translation key used in options list
# and strings.json entity.select.sg_ready.state.
SG_READY_OPTIONS: dict[int, str] = {
    0: "off_mode_0",
    1: "blocking_mode_1",
    2: "standard_mode_2",
    3: "boost_mode_3",
}
SG_READY_REVERSE: dict[str, int] = {v: k for k, v in SG_READY_OPTIONS.items()}

# SG-Ready mode-to-parameter write map. Imported concept from sg_ready.py but
# defined inline to avoid cross-package import (HA integration should not import
# from the proxy's src/ package).
# Mode -> {param_index: raw_value} (D-11)
SG_READY_MODE_MAP: dict[int, dict[int, int]] = {
    0: {3: 4, 4: 4},   # EVU lock: HeatingMode=Off, HotWaterMode=Off
    1: {3: 0, 4: 0},   # Normal: HeatingMode=Automatic, HotWaterMode=Automatic
    2: {3: 2, 4: 0},   # Recommended: HeatingMode=Party, HotWaterMode=Automatic
    3: {3: 0, 4: 2},   # Force on: HeatingMode=Automatic, HotWaterMode=Party
}


# ---------------------------------------------------------------------------
# Entity description dataclass
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LuxtronikSelectEntityDescription(SelectEntityDescription):
    """Extends HA SelectEntityDescription with Luxtronik-specific fields.

    Attributes:
        lux_index: Luxtronik parameter index for single-parameter selects.
            Set to -1 for virtual entities like SG-Ready that write multiple params.
        value_map: Mapping from raw integer to translation key string.
        reverse_map: Mapping from translation key string to raw integer.
        is_sg_ready: True for the SG-Ready virtual entity (uses dual-param write).
    """

    lux_index: int = 0
    value_map: dict[int, str] = field(default_factory=dict)
    reverse_map: dict[str, int] = field(default_factory=dict)
    is_sg_ready: bool = False


# ---------------------------------------------------------------------------
# Entity descriptions
# ---------------------------------------------------------------------------

SELECT_DESCRIPTIONS: tuple[LuxtronikSelectEntityDescription, ...] = (
    # CTRL-01, D-07: HeatingMode — parameter 3 (ID_Ba_Hz)
    LuxtronikSelectEntityDescription(
        key="heating_mode",
        icon="mdi:heat-pump",
        lux_index=3,
        value_map=MODE_OPTIONS,
        reverse_map=MODE_REVERSE,
    ),
    # CTRL-01, D-08: HotWaterMode — parameter 4 (ID_Ba_Bw)
    LuxtronikSelectEntityDescription(
        key="hot_water_mode",
        icon="mdi:heat-pump",
        lux_index=4,
        value_map=MODE_OPTIONS,
        reverse_map=MODE_REVERSE,
    ),
    # CTRL-02, D-10: SG-Ready virtual entity — writes params 3+4 atomically
    LuxtronikSelectEntityDescription(
        key="sg_ready",
        icon="mdi:solar-power",
        lux_index=-1,  # Virtual — no single parameter
        value_map=SG_READY_OPTIONS,
        reverse_map=SG_READY_REVERSE,
        is_sg_ready=True,
    ),
)


# ---------------------------------------------------------------------------
# Entity class
# ---------------------------------------------------------------------------


class LuxtronikSelectEntity(CoordinatorEntity[LuxtronikCoordinator], SelectEntity):
    """Select entity backed by the LuxtronikCoordinator.

    Uses has_entity_name=True and translation_key for localized entity names
    and option labels. The options list contains translation keys (e.g., "automatic",
    "party") — HA renders localized display strings from strings.json.

    For HeatingMode/HotWaterMode: reads raw int from coordinator.data["parameters"][lux_index],
    maps to translation key via value_map. Writes via coordinator.async_write_parameter.

    For SG-Ready: derives current mode by reverse-looking-up the parameter 3+4 combination
    in SG_READY_MODE_MAP. Writes via coordinator.async_write_parameters (atomic dual-param).
    """

    _attr_has_entity_name = True
    entity_description: LuxtronikSelectEntityDescription

    def __init__(
        self,
        coordinator: LuxtronikCoordinator,
        entry: ConfigEntry,
        description: LuxtronikSelectEntityDescription,
    ) -> None:
        """Initialize the select entity.

        Args:
            coordinator: The LuxtronikCoordinator providing poll data.
            entry: The config entry this entity belongs to.
            description: Metadata and value maps for this select entity.
        """
        super().__init__(coordinator)
        self.entity_description = description
        # Pitfall 6: Platform-discriminated unique_id avoids collision with sensor entities
        self._attr_unique_id = f"{entry.entry_id}_select_{description.key}"
        self._attr_translation_key = description.key

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info for grouping all entities under one device."""
        return DeviceInfo(
            identifiers={(DOMAIN, self.coordinator.config_entry.entry_id)},
            name=MODEL,
            manufacturer=MANUFACTURER,
            model=MODEL,
        )

    @property
    def options(self) -> list[str]:
        """Return list of available options (translation keys)."""
        return list(self.entity_description.value_map.values())

    @property
    def current_option(self) -> str | None:
        """Return the current selected option as a translation key.

        For HeatingMode/HotWaterMode: reads raw int from coordinator.data.
        For SG-Ready: reverse-looks up the param 3+4 combination to find matching mode.
        """
        desc = self.entity_description
        if desc.is_sg_ready:
            return self._get_sg_ready_current_option()

        raw = self.coordinator.data.get("parameters", {}).get(desc.lux_index)
        if raw is None:
            return None
        return desc.value_map.get(raw)

    def _get_sg_ready_current_option(self) -> str | None:
        """Derive current SG-Ready mode from parameters 3 and 4.

        Checks current HeatingMode (param 3) and HotWaterMode (param 4) against
        the SG_READY_MODE_MAP to find the matching SG-Ready mode. Returns None if
        the combination does not match any known mode.
        """
        params = self.coordinator.data.get("parameters", {})
        param_3 = params.get(3)
        param_4 = params.get(4)
        if param_3 is None or param_4 is None:
            return None
        for mode, param_map in SG_READY_MODE_MAP.items():
            if param_map.get(3) == param_3 and param_map.get(4) == param_4:
                return SG_READY_OPTIONS[mode]
        return None  # Current combination does not match any SG-Ready mode

    async def async_select_option(self, option: str) -> None:
        """Handle user selecting an option. Write to the Luxtronik controller.

        For HeatingMode/HotWaterMode (D-09): writes single parameter via
        coordinator.async_write_parameter.

        For SG-Ready (D-11): writes parameters 3 AND 4 atomically via
        coordinator.async_write_parameters.

        Args:
            option: The selected option (translation key, e.g., "automatic" or "boost_mode_3").
        """
        desc = self.entity_description
        if desc.is_sg_ready:
            mode = SG_READY_REVERSE[option]
            await self.coordinator.async_write_parameters(SG_READY_MODE_MAP[mode])
        else:
            raw_value = desc.reverse_map[option]
            await self.coordinator.async_write_parameter(desc.lux_index, raw_value)


# ---------------------------------------------------------------------------
# Platform setup
# ---------------------------------------------------------------------------


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Luxtronik select entities from a config entry.

    Args:
        hass: The Home Assistant instance.
        entry: The config entry to set up.
        async_add_entities: Callback to register entity objects with HA.
    """
    coordinator: LuxtronikCoordinator = hass.data[DOMAIN][entry.entry_id]
    entities = [
        LuxtronikSelectEntity(coordinator, entry, desc)
        for desc in SELECT_DESCRIPTIONS
    ]
    _LOGGER.debug("Registered %d select entities", len(entities))
    async_add_entities(entities)
