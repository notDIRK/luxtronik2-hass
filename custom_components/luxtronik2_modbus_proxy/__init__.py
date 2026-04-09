"""Luxtronik 2 Modbus Proxy integration for Home Assistant.

Wires the config entry lifecycle to the LuxtronikCoordinator:

- D-12: ``async_setup_entry`` creates a coordinator, runs the first data
  refresh (raising ConfigEntryNotReady on failure so HA retries), and stores
  the coordinator in ``hass.data[DOMAIN][entry.entry_id]`` for use by entity
  platforms.
- D-13: ``async_unload_entry`` unloads all entity platforms and removes the
  coordinator from ``hass.data``.
- D-14: ``PLATFORMS`` lists the ``sensor``, ``select``, and ``number`` entity
  platforms.
"""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant

from .const import DEFAULT_PORT, DOMAIN
from .coordinator import LuxtronikCoordinator

_LOGGER = logging.getLogger(__name__)

# Entity platforms: sensor (Phase 6), select + number (Phase 7).
PLATFORMS: list[str] = ["sensor", "select", "number"]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Luxtronik 2 Modbus Proxy from a config entry.

    Called by HA when a config entry is loaded (on startup or after being added
    via the config flow). Creates a LuxtronikCoordinator, performs the first
    data refresh, stores the coordinator in hass.data, and forwards platform
    setup to the (currently empty) PLATFORMS list. (D-12)

    Args:
        hass: The Home Assistant instance.
        entry: The config entry being set up.

    Returns:
        True if setup succeeded.

    Raises:
        ConfigEntryNotReady: Propagated from coordinator.async_config_entry_first_refresh()
            if the initial connection to the Luxtronik controller fails. HA will
            automatically retry the setup using an exponential backoff schedule.
    """
    host: str = entry.data[CONF_HOST]
    port: int = entry.data.get("port", DEFAULT_PORT)

    coordinator = LuxtronikCoordinator(hass, entry, host, port)

    # Run first refresh before storing the coordinator.
    # If the controller is unreachable, this raises ConfigEntryNotReady,
    # which HA catches and retries — entities are shown as unavailable until
    # the controller comes back online.
    await coordinator.async_config_entry_first_refresh()

    # Register update listener before storing the coordinator.
    # When the Options Flow saves new values (host or poll_interval),
    # HA fires this listener, triggering a full unload+setup cycle so the
    # coordinator reconnects with the updated settings immediately.
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    # D-12: Store coordinator keyed by entry_id so entity platforms can retrieve it.
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    # D-14: Forward to entity platforms (sensor, select, number).
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a Luxtronik 2 Modbus Proxy config entry.

    Called by HA when the user removes the integration or HA is shutting down.
    Unloads all entity platforms and removes the coordinator from hass.data. (D-13)

    Args:
        hass: The Home Assistant instance.
        entry: The config entry being unloaded.

    Returns:
        True if all platforms unloaded successfully, False otherwise.
    """
    unload_ok: bool = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if unload_ok:
        # D-13: Remove coordinator from shared data store.
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload the config entry when options change.

    Triggered by the Options Flow saving new values (host or poll_interval).
    A full reload recreates the coordinator with the updated host/port and
    poll interval, ensuring the new settings take effect immediately.

    Args:
        hass: The Home Assistant instance.
        entry: The config entry that was updated.
    """
    await hass.config_entries.async_reload(entry.entry_id)
