"""Sensor platform for the Luxtronik 2 Modbus Proxy Home Assistant integration.

Exposes Luxtronik 2.0 heat pump data as HA sensor entities:

- Core sensors (enabled by default): 6 temperature sensors, 1 operating mode,
  2 status sensors (compressor/pump), 1 conditional power sensor. (SENS-01 to SENS-03)
- Disabled-by-default sensors: all 251 calculations and 1,126 parameters from the
  full register database, allowing users to enable individual data points via the
  HA entity registry UI. (SENS-04)

All raw integer values come from coordinator.data (dict[int, int]) and are converted
to display values via the luxtronik library's from_heatpump() method. See the
conversion chain reference in 06-RESEARCH.md.

Data flow:
    Controller wire int -> coordinator._sync_read() [to_heatpump()] -> raw int stored
    -> coordinator.data["calculations"][idx] or ["parameters"][idx]
    -> entity native_value: from_heatpump(raw_int) -> display value
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Callable

import luxtronik.calculations as _lc
import luxtronik.parameters as _lp

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER, MODEL
from .coordinator import LuxtronikCoordinator

_LOGGER = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Luxtronik datatype library objects — instantiated ONCE at module load.
# These are the conversion objects used by value_fn callables.
# Using a single Calculations() / Parameters() instance avoids repeated
# library init cost when building the 1,377 entity descriptions. (Pitfall 6)
# ---------------------------------------------------------------------------
_lux_calcs = _lc.Calculations()
_lux_params = _lp.Parameters()


# ---------------------------------------------------------------------------
# LuxtronikSensorEntityDescription
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LuxtronikSensorEntityDescription(SensorEntityDescription):
    """Extends HA SensorEntityDescription with Luxtronik-specific fields.

    Attributes:
        data_source: Which coordinator.data key to read from.
            Either ``"calculations"`` (read-only computed values) or
            ``"parameters"`` (read/write controller parameters).
        lux_index: Luxtronik library index for this data point.
            Used as the key into coordinator.data[data_source].
        value_fn: Optional callable ``(raw_int) -> display_value`` wrapping the
            luxtronik datatype's ``from_heatpump()`` method.
            If None, the raw integer value is returned directly.
    """

    data_source: str = "calculations"
    lux_index: int = 0
    value_fn: Callable[[int], Any] | None = None


# ---------------------------------------------------------------------------
# Core sensor descriptions (SENS-01 to SENS-04)
# Enabled by default (entity_registry_enabled_default=True, the HA default)
# ---------------------------------------------------------------------------

# D-01: Temperature sensors — 6 core temperature measurements.
# All use SensorDeviceClass.TEMPERATURE, native °C, MEASUREMENT state class, 1 decimal.
# from_heatpump(raw_int) returns float (divides by 10 internally for Celsius type).

CORE_SENSOR_DESCRIPTIONS: tuple[LuxtronikSensorEntityDescription, ...] = (
    # SENS-01: Outside temperature — Luxtronik calculation index 15 (ID_WEB_Temperatur_TA)
    LuxtronikSensorEntityDescription(
        key="outside_temperature",
        name="Luxtronik Outside Temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement="°C",
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        icon="mdi:thermometer",
        data_source="calculations",
        lux_index=15,
        value_fn=_lux_calcs.calculations[15].from_heatpump,  # D-01, D-16
    ),
    # SENS-01: Flow temperature — calculation index 10 (ID_WEB_Temperatur_TVL)
    LuxtronikSensorEntityDescription(
        key="flow_temperature",
        name="Luxtronik Flow Temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement="°C",
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        icon="mdi:thermometer-chevron-up",
        data_source="calculations",
        lux_index=10,
        value_fn=_lux_calcs.calculations[10].from_heatpump,  # D-01, D-16
    ),
    # SENS-01: Return temperature — calculation index 11 (ID_WEB_Temperatur_TRL)
    LuxtronikSensorEntityDescription(
        key="return_temperature",
        name="Luxtronik Return Temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement="°C",
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        icon="mdi:thermometer-chevron-down",
        data_source="calculations",
        lux_index=11,
        value_fn=_lux_calcs.calculations[11].from_heatpump,  # D-01, D-16
    ),
    # SENS-01: Hot water tank temperature — calculation index 17 (ID_WEB_Temperatur_TBW)
    LuxtronikSensorEntityDescription(
        key="hot_water_temperature",
        name="Luxtronik Hot Water Temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement="°C",
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        icon="mdi:water-thermometer",
        data_source="calculations",
        lux_index=17,
        value_fn=_lux_calcs.calculations[17].from_heatpump,  # D-01, D-16
    ),
    # SENS-01: Source inlet temperature — calculation index 19 (ID_WEB_Temperatur_TWE)
    LuxtronikSensorEntityDescription(
        key="source_in_temperature",
        name="Luxtronik Source Inlet Temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement="°C",
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        icon="mdi:thermometer-water",
        data_source="calculations",
        lux_index=19,
        value_fn=_lux_calcs.calculations[19].from_heatpump,  # D-01, D-16
    ),
    # SENS-01: Source outlet temperature — calculation index 20 (ID_WEB_Temperatur_TWA)
    LuxtronikSensorEntityDescription(
        key="source_out_temperature",
        name="Luxtronik Source Outlet Temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement="°C",
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        icon="mdi:thermometer-water",
        data_source="calculations",
        lux_index=20,
        value_fn=_lux_calcs.calculations[20].from_heatpump,  # D-01, D-16
    ),
    # SENS-02, D-02: Operating mode — calculation index 80 (ID_WEB_WP_BZ_akt).
    # from_heatpump() returns lowercase string ("heating", "hot water", etc.)
    # Apply .title() to match D-02 spec: "Heating", "Hot Water", "Defrost", etc.
    # See Pitfall 3 in RESEARCH.md for details on the lowercase-to-title transform.
    LuxtronikSensorEntityDescription(
        key="operating_mode",
        name="Luxtronik Operating Mode",
        icon="mdi:heat-pump",
        data_source="calculations",
        lux_index=80,
        value_fn=lambda raw: (  # D-02, D-18
            _lux_calcs.calculations[80].from_heatpump(raw).title()
            if _lux_calcs.calculations[80].from_heatpump(raw) is not None
            else None
        ),
    ),
    # SENS-02, D-03: Compressor status — calculation index 44 (ID_WEB_VD1out).
    # from_heatpump() returns Python bool. D-03 requires "Running"/"Stopped" strings.
    # See Pitfall 4 in RESEARCH.md for the bool-to-string conversion requirement.
    LuxtronikSensorEntityDescription(
        key="compressor_running",
        name="Luxtronik Compressor",
        icon="mdi:engine",
        data_source="calculations",
        lux_index=44,
        value_fn=lambda raw: (  # D-03, D-18
            "Running" if _lux_calcs.calculations[44].from_heatpump(raw) else "Stopped"
        ),
    ),
    # SENS-02, D-03: Circulation pump status — calculation index 39 (ID_WEB_HUPout).
    # Same bool-to-string conversion pattern as compressor (D-03).
    LuxtronikSensorEntityDescription(
        key="circulation_pump_running",
        name="Luxtronik Circulation Pump",
        icon="mdi:pump",
        data_source="calculations",
        lux_index=39,
        value_fn=lambda raw: (  # D-03, D-18
            "Running" if _lux_calcs.calculations[39].from_heatpump(raw) else "Stopped"
        ),
    ),
    # SENS-03, D-04: Heat pump power output — calculation index 257 (Heat_Output).
    # from_heatpump() returns int in Watts.
    # CONDITIONAL: Only added to entities if index 257 exists in coordinator.data.
    # See async_setup_entry and Pitfall 2 in RESEARCH.md for the conditional guard.
    LuxtronikSensorEntityDescription(
        key="heat_pump_power",
        name="Luxtronik Heat Pump Power",
        device_class=SensorDeviceClass.POWER,
        native_unit_of_measurement="W",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:lightning-bolt",
        data_source="calculations",
        lux_index=257,
        value_fn=_lux_calcs.calculations[257].from_heatpump,  # D-04, D-17
    ),
)

# ---------------------------------------------------------------------------
# Disabled-by-default sensor descriptions (SENS-04)
# Core calculation indices — skip these when building the "all calcs" list.
# These 10 indices are already covered by CORE_SENSOR_DESCRIPTIONS above.
# ---------------------------------------------------------------------------

_CORE_CALC_INDICES: frozenset[int] = frozenset({10, 11, 15, 17, 19, 20, 39, 44, 80, 257})


def _build_extra_calc_descriptions() -> tuple[LuxtronikSensorEntityDescription, ...]:
    """Build disabled-by-default descriptions for non-core calculations.

    Iterates all 251 calculation objects from the luxtronik library, skipping
    the 10 core indices already covered by CORE_SENSOR_DESCRIPTIONS. Each
    description uses entity_registry_enabled_default=False (D-08) and
    EntityCategory.DIAGNOSTIC.

    Returns:
        A tuple of LuxtronikSensorEntityDescription, one per non-core calculation.
    """
    descs: list[LuxtronikSensorEntityDescription] = []
    for idx, calc_obj in _lux_calcs.calculations.items():
        if idx in _CORE_CALC_INDICES or calc_obj is None:
            continue
        if not hasattr(calc_obj, "from_heatpump"):
            continue

        # Determine device class and unit from luxtronik type name.
        data_type = type(calc_obj).__name__
        device_class: SensorDeviceClass | None = None
        unit: str | None = None
        state_class: SensorStateClass | None = None
        if data_type == "Celsius":
            device_class = SensorDeviceClass.TEMPERATURE
            unit = "°C"
            state_class = SensorStateClass.MEASUREMENT
        elif data_type == "Power":
            device_class = SensorDeviceClass.POWER
            unit = "W"
            state_class = SensorStateClass.MEASUREMENT

        calc_name = getattr(calc_obj, "name", f"Calculation {idx}")

        descs.append(
            LuxtronikSensorEntityDescription(
                key=f"calc_{idx}",
                name=f"Luxtronik {calc_name}",  # D-11: derived from library name
                device_class=device_class,
                native_unit_of_measurement=unit,
                state_class=state_class,
                entity_registry_enabled_default=False,  # D-08
                entity_category=EntityCategory.DIAGNOSTIC,
                data_source="calculations",
                lux_index=idx,
                value_fn=calc_obj.from_heatpump,
            )
        )
    return tuple(descs)


def _build_param_descriptions() -> tuple[LuxtronikSensorEntityDescription, ...]:
    """Build disabled-by-default descriptions for all 1,126 parameters.

    Iterates all parameter objects from the luxtronik library. Each description
    uses entity_registry_enabled_default=False (D-08) and EntityCategory.DIAGNOSTIC.

    Returns:
        A tuple of LuxtronikSensorEntityDescription, one per parameter.
    """
    descs: list[LuxtronikSensorEntityDescription] = []
    for idx, param_obj in _lux_params.parameters.items():
        if param_obj is None:
            continue
        if not hasattr(param_obj, "from_heatpump"):
            continue

        # Determine device class and unit from luxtronik type name.
        data_type = type(param_obj).__name__
        device_class: SensorDeviceClass | None = None
        unit: str | None = None
        state_class: SensorStateClass | None = None
        if data_type == "Celsius":
            device_class = SensorDeviceClass.TEMPERATURE
            unit = "°C"
            state_class = SensorStateClass.MEASUREMENT

        param_name = getattr(param_obj, "name", f"Parameter {idx}")

        descs.append(
            LuxtronikSensorEntityDescription(
                key=f"param_{idx}",
                name=f"Luxtronik {param_name}",  # D-11: derived from library name
                device_class=device_class,
                native_unit_of_measurement=unit,
                state_class=state_class,
                entity_registry_enabled_default=False,  # D-08
                entity_category=EntityCategory.DIAGNOSTIC,
                data_source="parameters",
                lux_index=idx,
                value_fn=param_obj.from_heatpump,
            )
        )
    return tuple(descs)


# Build at module load time. Cost is acceptable — pure Python, no I/O. (Pitfall 6)
ALL_EXTRA_CALC_DESCRIPTIONS: tuple[LuxtronikSensorEntityDescription, ...] = (
    _build_extra_calc_descriptions()
)
ALL_PARAM_DESCRIPTIONS: tuple[LuxtronikSensorEntityDescription, ...] = (
    _build_param_descriptions()
)


# ---------------------------------------------------------------------------
# LuxtronikSensorEntity
# ---------------------------------------------------------------------------


class LuxtronikSensorEntity(CoordinatorEntity[LuxtronikCoordinator], SensorEntity):
    """A single Luxtronik sensor entity backed by the DataUpdateCoordinator.

    Reads raw integer values from coordinator.data and converts them to HA
    display values via the luxtronik library's from_heatpump() method, pre-captured
    in the entity description's value_fn. (D-12, D-13)
    """

    entity_description: LuxtronikSensorEntityDescription

    def __init__(
        self,
        coordinator: LuxtronikCoordinator,
        entry: ConfigEntry,
        description: LuxtronikSensorEntityDescription,
    ) -> None:
        """Initialize the sensor entity.

        Args:
            coordinator: The LuxtronikCoordinator providing poll data.
            entry: The config entry this entity belongs to.
            description: Metadata and conversion function for this sensor.
        """
        super().__init__(coordinator)
        self.entity_description = description

        # D-07 deviation: Original spec says `{config_entry_id}_{lux_index}`.
        # However, calculations and parameters share overlapping index spaces
        # (both start at 0), so index alone is not unique. This implementation
        # adds the data_source discriminator to guarantee stable unique IDs:
        # `{entry_id}_{data_source}_{lux_index}`.
        # Example: "abc123_calculations_15" vs "abc123_parameters_15" — distinct.
        self._attr_unique_id = (
            f"{entry.entry_id}_{description.data_source}_{description.lux_index}"
        )

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info for grouping all entities under one device. (D-14, D-15)

        All entities share a single device per config entry, identified by the
        combination of DOMAIN and entry_id so that multiple config entries (if
        ever supported) produce separate devices.
        """
        return DeviceInfo(
            identifiers={(DOMAIN, self.coordinator.config_entry.entry_id)},
            name=MODEL,
            manufacturer=MANUFACTURER,
            model=MODEL,
        )

    @property
    def native_value(self) -> Any:
        """Return the sensor's display value.

        Reads the raw integer from coordinator.data[data_source][lux_index], then
        passes it through the description's value_fn (wrapping from_heatpump()) to
        produce the HA display value.

        Returns None if the index is absent from coordinator.data (e.g., controller
        did not provide that data point in the current poll cycle). The CoordinatorEntity
        base class marks the entity as unavailable if coordinator.last_update_success
        is False, so None here means the data point is genuinely absent this poll.
        """
        desc = self.entity_description
        data_dict: dict[int, int] = self.coordinator.data.get(desc.data_source, {})
        raw_val = data_dict.get(desc.lux_index)
        if raw_val is None:
            return None
        if desc.value_fn is not None:
            return desc.value_fn(raw_val)
        return raw_val


# ---------------------------------------------------------------------------
# Platform setup
# ---------------------------------------------------------------------------


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Luxtronik sensor entities from a config entry. (D-19, D-20)

    Retrieves the coordinator from hass.data (stored by __init__.py async_setup_entry),
    creates entity objects for core sensors and all disabled-by-default sensors,
    and registers them with HA via async_add_entities.

    Args:
        hass: The Home Assistant instance.
        entry: The config entry to set up.
        async_add_entities: Callback to register entity objects with HA.
    """
    coordinator: LuxtronikCoordinator = hass.data[DOMAIN][entry.entry_id]

    entities: list[LuxtronikSensorEntity] = []

    # SENS-01 to SENS-03: Core sensors — always enabled, conditionally include power.
    for desc in CORE_SENSOR_DESCRIPTIONS:
        # SENS-03, D-04: Power sensor (index 257) is conditional.
        # Only add if the controller provided index 257 in the first poll.
        # See Pitfall 2 in RESEARCH.md. If coordinator data is empty (first refresh
        # failed), async_config_entry_first_refresh() would have raised before reaching
        # here — so coordinator.data is guaranteed non-None at this point.
        if desc.lux_index == 257 and 257 not in coordinator.data.get("calculations", {}):
            _LOGGER.debug(
                "Skipping heat_pump_power sensor: calculation index 257 not present "
                "in coordinator data (controller may not support Heat_Output)"
            )
            continue
        entities.append(LuxtronikSensorEntity(coordinator, entry, desc))

    # SENS-04: All remaining calculations — disabled by default.
    entities.extend(
        LuxtronikSensorEntity(coordinator, entry, desc)
        for desc in ALL_EXTRA_CALC_DESCRIPTIONS
    )

    # SENS-04: All parameters — disabled by default.
    entities.extend(
        LuxtronikSensorEntity(coordinator, entry, desc)
        for desc in ALL_PARAM_DESCRIPTIONS
    )

    _LOGGER.debug(
        "Registered %d sensor entities (%d core, %d extra calcs, %d params)",
        len(entities),
        len(CORE_SENSOR_DESCRIPTIONS),  # actual registered may be 9 if power skipped
        len(ALL_EXTRA_CALC_DESCRIPTIONS),
        len(ALL_PARAM_DESCRIPTIONS),
    )

    async_add_entities(entities)
