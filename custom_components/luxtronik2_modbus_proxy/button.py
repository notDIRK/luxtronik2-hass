"""Button platform for the Luxtronik 2 Modbus Proxy Home Assistant integration.

Provides a "Backup Parameters" button that reads all 1,126 parameters from the
Luxtronik 2.0 controller and saves them as a timestamped JSON file. This gives
users a safety snapshot before making configuration changes.

Backup workflow:
1. User presses the button in HA.
2. async_press() acquires coordinator._lock (ARCH-03) and dispatches a blocking
   read to the executor thread pool (ARCH-02).
3. _sync_backup() creates a fresh luxtronik.Luxtronik instance (ARCH-01 pattern)
   to read all parameters directly from the controller.
4. JSON file is written to {ha_config}/luxtronik2_backups/YYYY-MM-DD_HH-MM-SS.json.
5. Backup metadata (timestamp, filename) is stored in hass.data for consumption
   by the LuxtronikLastBackupSensor in sensor.py.
6. A dispatcher signal fires so the sensor entity updates immediately.
7. A persistent_notification is created with the backup summary.
"""

from __future__ import annotations

import datetime
import json
import logging
import os

import luxtronik

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import BACKUP_DIR, DOMAIN, MANUFACTURER, MODEL
from .coordinator import LuxtronikCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Luxtronik button entities from a config entry.

    Creates and registers the backup parameters button for this integration entry.

    Args:
        hass: The Home Assistant instance.
        entry: The config entry to set up.
        async_add_entities: Callback to register entity objects with HA.
    """
    coordinator: LuxtronikCoordinator = hass.data[DOMAIN][entry.entry_id]
    button = LuxtronikBackupButton(hass, coordinator, entry)
    async_add_entities([button])


class LuxtronikBackupButton(ButtonEntity):
    """Button entity that triggers a full parameter backup.

    When pressed, reads all parameters from the Luxtronik controller via the
    same __new__ pattern used by the coordinator (ARCH-01), saves a JSON file,
    and notifies the user via a persistent_notification. Stores backup metadata
    in hass.data so that LuxtronikLastBackupSensor (sensor.py) can display it.

    Appears under the device's "Configuration" section in HA (EntityCategory.CONFIG).
    """

    _attr_name = "Luxtronik Backup Parameters"
    _attr_icon = "mdi:content-save-all"
    _attr_entity_category = EntityCategory.CONFIG
    _attr_has_entity_name = False

    def __init__(
        self,
        hass: HomeAssistant,
        coordinator: LuxtronikCoordinator,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the backup button.

        Args:
            hass: The Home Assistant instance.
            coordinator: The LuxtronikCoordinator that owns the controller connection.
            entry: The config entry this entity belongs to.
        """
        self.hass = hass
        self._coordinator = coordinator
        self._entry = entry
        self._entry_id = entry.entry_id
        self._host = coordinator._host
        self._port = coordinator._port
        self._attr_unique_id = f"{entry.entry_id}_backup_parameters"

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info for grouping this entity under the heat pump device.

        Uses the same identifiers as sensor.py so all entities appear under one device.
        """
        return DeviceInfo(
            identifiers={(DOMAIN, self._coordinator.config_entry.entry_id)},
            name=MODEL,
            manufacturer=MANUFACTURER,
            model=MODEL,
        )

    async def async_press(self) -> None:
        """Handle button press — perform full parameter backup.

        Acquires coordinator._lock (ARCH-03) before connecting to the controller
        to serialize with ongoing reads and writes. Dispatches the blocking I/O
        to the executor thread pool (ARCH-02).

        After backup:
        - Stores metadata in hass.data[DOMAIN][f"{entry_id}_last_backup"].
        - Sends dispatcher signal so LuxtronikLastBackupSensor refreshes.
        - Creates a persistent_notification with the backup summary.
        """
        async with self._coordinator._lock:  # ARCH-03: serialize TCP access
            try:
                filename, timestamp, count = await self.hass.async_add_executor_job(
                    self._sync_backup
                )
            except Exception as err:
                _LOGGER.error(
                    "Parameter backup failed for Luxtronik at %s: %s",
                    self._host,
                    err,
                )
                self.hass.components.persistent_notification.async_create(
                    message=f"Backup failed: {err}",
                    title="Luxtronik Parameter Backup Failed",
                    notification_id=f"{DOMAIN}_backup_error",
                )
                return

        # Store backup metadata for the last-backup sensor to read.
        self.hass.data.setdefault(DOMAIN, {})[
            f"{self._entry_id}_last_backup"
        ] = {
            "timestamp": timestamp,
            "filename": filename,
        }

        # Notify the backup sensor to refresh its state immediately.
        async_dispatcher_send(
            self.hass,
            f"{DOMAIN}_backup_complete",
            {"timestamp": timestamp, "filename": filename},
        )

        # Inform the user via a persistent notification in the HA UI.
        self.hass.components.persistent_notification.async_create(
            message=(
                f"Backed up {count} parameters to `{filename}`\n"
                f"Timestamp: {timestamp}"
            ),
            title="Luxtronik Parameter Backup Complete",
            notification_id=f"{DOMAIN}_backup",
        )
        _LOGGER.info(
            "Luxtronik parameter backup complete: %d parameters -> %s",
            count,
            filename,
        )

    def _sync_backup(self) -> tuple[str, str, int]:
        """Read all parameters and write a JSON backup file (runs in executor).

        Creates a fresh luxtronik.Luxtronik instance using the __new__ pattern
        (ARCH-01) — same as coordinator._sync_read — to avoid the auto-read call
        in Luxtronik.__init__. Reads all parameters then immediately discards the
        instance, releasing the TCP connection.

        JSON structure written to disk:
            {
                "timestamp": "<ISO 8601 UTC>",
                "host": "<controller IP>",
                "parameters": {
                    "<index>": {
                        "name": "<param name>",
                        "type": "<luxtronik datatype>",
                        "raw_value": <int or null>,
                        "display_value": "<str or null>"
                    },
                    ...
                }
            }

        Returns:
            Tuple of (filename, iso_timestamp, parameter_count).

        Raises:
            OSError: If the backup directory cannot be created or the file cannot
                be written.
            Exception: Propagated from luxtronik.read() on connection failure.
        """
        # ARCH-01: Use __new__ to bypass Luxtronik.__init__ auto-read.
        lux = luxtronik.Luxtronik.__new__(luxtronik.Luxtronik)
        lux._host = self._host
        lux._port = self._port
        lux._socket = None
        lux.calculations = luxtronik.Calculations()
        lux.parameters = luxtronik.Parameters()
        lux.visibilities = luxtronik.Visibilities()
        lux.read()  # blocking — OK, running in executor thread

        # Build the parameter dict with name, type, raw, and display values.
        params_dict: dict[str, dict] = {}
        for idx, param_obj in lux.parameters.parameters.items():
            if param_obj is None:
                continue
            entry: dict = {
                "name": getattr(param_obj, "name", f"Parameter {idx}"),
                "type": type(param_obj).__name__,
            }
            if hasattr(param_obj, "to_heatpump") and param_obj.value is not None:
                try:
                    entry["raw_value"] = int(param_obj.to_heatpump(param_obj.value))
                except (TypeError, ValueError, AttributeError):
                    entry["raw_value"] = None
            else:
                entry["raw_value"] = None
            entry["display_value"] = (
                str(param_obj.value) if param_obj.value is not None else None
            )
            params_dict[str(idx)] = entry

        # Assemble the full backup payload.
        now = datetime.datetime.now(datetime.timezone.utc)
        filename = now.strftime("%Y-%m-%d_%H-%M-%S") + ".json"
        backup = {
            "timestamp": now.isoformat(),
            "host": self._host,
            "parameters": params_dict,
        }

        # Write to {ha_config}/luxtronik2_backups/<filename>.
        backup_path = self.hass.config.path(BACKUP_DIR)
        os.makedirs(backup_path, exist_ok=True)
        filepath = os.path.join(backup_path, filename)
        with open(filepath, "w", encoding="utf-8") as fh:
            json.dump(backup, fh, indent=2, ensure_ascii=False)

        _LOGGER.debug(
            "Wrote %d parameters to %s", len(params_dict), filepath
        )
        return filename, now.isoformat(), len(params_dict)
