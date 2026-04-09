"""Number platform for the Luxtronik 2 Modbus Proxy Home Assistant integration.

Provides number entities for temperature setpoint control:

- Hot Water Setpoint (parameter 105, ID_Soll_BWS_akt): 30.0-65.0 C, step 0.5 (CTRL-03, D-14)
- Heating Curve Offset (parameter 1, ID_Einst_WK_akt): -5.0 to 5.0 C, step 0.5 (CTRL-03, D-15)

Both parameters use the Celsius data type where raw_value = display_value * 10
(e.g., 50.0 C is stored as 500). The entity's native_value divides by 10 for display,
and set_native_value multiplies by 10 for write. (D-16)

All writes route through coordinator.async_write_parameter() which enforces
the single-connection constraint (ARCH-03) and NAND flash rate limiting (CTRL-04).

Entity names are localized via translation_key + strings.json.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from homeassistant.components.number import (
    NumberDeviceClass,
    NumberEntity,
    NumberEntityDescription,
    NumberMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER, MODEL
from .coordinator import LuxtronikCoordinator

_LOGGER = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# LuxtronikNumberEntityDescription
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LuxtronikNumberEntityDescription(NumberEntityDescription):
    """Extends HA NumberEntityDescription with Luxtronik-specific fields.

    Attributes:
        lux_index: Luxtronik parameter index for this setpoint.
        raw_multiplier: Multiplier to convert display value to raw integer.
            For Celsius type: raw = display * 10 (D-16).
    """

    lux_index: int = 0
    raw_multiplier: int = 10


# ---------------------------------------------------------------------------
# Number entity descriptions
# ---------------------------------------------------------------------------

NUMBER_DESCRIPTIONS: tuple[LuxtronikNumberEntityDescription, ...] = (
    # CTRL-03, D-14: Hot water setpoint — parameter 105 (ID_Soll_BWS_akt)
    # Range 30.0-65.0 C verified from register_definitions/parameters.py (min_value=300, max_value=650)
    LuxtronikNumberEntityDescription(
        key="hot_water_setpoint",
        icon="mdi:thermometer",
        device_class=NumberDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        native_min_value=30.0,
        native_max_value=65.0,
        native_step=0.5,
        mode=NumberMode.BOX,
        entity_category=EntityCategory.CONFIG,
        lux_index=105,
        raw_multiplier=10,
    ),
    # CTRL-03, D-15: Heating curve offset — parameter 1 (ID_Einst_WK_akt)
    # Range -5.0 to 5.0 C (ASSUMED — typical Luxtronik 2.0 heating curve offset limits, A1)
    LuxtronikNumberEntityDescription(
        key="heating_curve_offset",
        icon="mdi:thermometer",
        device_class=NumberDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        native_min_value=-5.0,
        native_max_value=5.0,
        native_step=0.5,
        mode=NumberMode.BOX,
        entity_category=EntityCategory.CONFIG,
        lux_index=1,
        raw_multiplier=10,
    ),
)


# ---------------------------------------------------------------------------
# LuxtronikNumberEntity
# ---------------------------------------------------------------------------


class LuxtronikNumberEntity(CoordinatorEntity[LuxtronikCoordinator], NumberEntity):
    """Number entity for temperature setpoints backed by the LuxtronikCoordinator.

    Uses has_entity_name=True and translation_key for localized entity names.
    Display values are in degrees Celsius; raw values sent to the controller are
    multiplied by raw_multiplier (10 for Celsius type). (D-16)
    """

    _attr_has_entity_name = True
    entity_description: LuxtronikNumberEntityDescription

    def __init__(
        self,
        coordinator: LuxtronikCoordinator,
        entry: ConfigEntry,
        description: LuxtronikNumberEntityDescription,
    ) -> None:
        """Initialize the number entity.

        Args:
            coordinator: The LuxtronikCoordinator providing poll data.
            entry: The config entry this entity belongs to.
            description: Metadata and range constraints for this number entity.
        """
        super().__init__(coordinator)
        self.entity_description = description
        # Platform-discriminated unique_id avoids collision with sensor entities
        self._attr_unique_id = f"{entry.entry_id}_number_{description.key}"
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
    def native_value(self) -> float | None:
        """Return the current setpoint value in display units (degrees C).

        Reads the raw integer from coordinator.data["parameters"][lux_index]
        and divides by raw_multiplier (10) to get the display value. (D-16)
        """
        desc = self.entity_description
        raw = self.coordinator.data.get("parameters", {}).get(desc.lux_index)
        if raw is None:
            return None
        return raw / desc.raw_multiplier

    async def async_set_native_value(self, value: float) -> None:
        """Set the temperature setpoint. Write to the Luxtronik controller.

        Converts the display value to raw integer by multiplying by raw_multiplier
        (e.g., 50.0 C -> 500 raw), then writes via coordinator. (D-16)

        Args:
            value: The new setpoint value in display units (degrees C).
        """
        desc = self.entity_description
        raw = int(value * desc.raw_multiplier)
        await self.coordinator.async_write_parameter(desc.lux_index, raw)


# ---------------------------------------------------------------------------
# Platform setup
# ---------------------------------------------------------------------------


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Luxtronik number entities from a config entry.

    Args:
        hass: The Home Assistant instance.
        entry: The config entry to set up.
        async_add_entities: Callback to register entity objects with HA.
    """
    coordinator: LuxtronikCoordinator = hass.data[DOMAIN][entry.entry_id]
    entities = [
        LuxtronikNumberEntity(coordinator, entry, desc)
        for desc in NUMBER_DESCRIPTIONS
    ]
    _LOGGER.debug("Registered %d number entities", len(entities))
    async_add_entities(entities)
