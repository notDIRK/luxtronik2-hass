"""Config flow for Luxtronik 2 Modbus Proxy integration.

Implements a single-step user flow where the user enters the IP address of
their Luxtronik 2.0 heat pump controller. The flow performs three checks
before creating a config entry:

- D-06: Single-field form — only CONF_HOST (IP address) is shown in the UI.
- D-07: port and poll_interval are stored in the config entry data but are
  NOT exposed in the form, keeping the UX simple.
- D-08 (SETUP-03): A blocking connection test via the luxtronik library
  verifies reachability on port 8889 before creating the entry.
- D-09 (SETUP-04): Checks for an existing BenPru/luxtronik config entry for
  the same IP address and aborts with a descriptive message to prevent
  simultaneous connections that would cause TCP conflicts.
- D-11: Sets the config entry unique ID to the host IP so that HA's built-in
  deduplication blocks a second entry for the same controller.
"""

from __future__ import annotations

import logging
from typing import Any

import luxtronik
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_HOST

from .const import DEFAULT_POLL_INTERVAL, DEFAULT_PORT, DOMAIN

_LOGGER = logging.getLogger(__name__)


class LuxtronikConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle the Luxtronik 2 Modbus Proxy integration config flow.

    Single-step flow: the user provides the heat pump controller's IP address.
    The flow validates reachability and BenPru/luxtronik coexistence before
    creating a config entry that starts the LuxtronikCoordinator in __init__.py.
    """

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        """Handle the initial user step.

        Presents the IP address form. On submission, validates the input in
        order: unique-ID dedup (D-11), BenPru conflict detection (D-09, SETUP-04),
        then connection test (D-08, SETUP-03).

        Args:
            user_input: Form data supplied by HA's UI, or None on first render.

        Returns:
            A FlowResult — either show_form to re-render, async_abort to halt,
            or async_create_entry to finish.
        """
        errors: dict[str, str] = {}

        if user_input is not None:
            # Whitespace safety per UI-SPEC (T-05-05: strip before TCP connection)
            host: str = user_input[CONF_HOST].strip()

            # D-11: Set unique ID to host IP and abort if already configured
            # (prevents duplicate own-integration entries for the same controller)
            await self.async_set_unique_id(host)
            self._abort_if_unique_id_configured()

            # D-09 (SETUP-04): BenPru conflict detection.
            # The BenPru/luxtronik integration uses domain "luxtronik" (NOT our domain).
            # Running both integrations on the same controller causes TCP conflicts because
            # Luxtronik 2.0 allows exactly one connection at a time.
            for entry in self.hass.config_entries.async_entries("luxtronik"):
                if entry.data.get("host") == host:
                    return self.async_abort(reason="already_configured_benPru")

            # D-08 (SETUP-03): Connection test in executor.
            # The luxtronik library is synchronous (blocking socket I/O). Running via
            # async_add_executor_job prevents blocking the HA event loop. (T-05-07)
            try:
                await self.hass.async_add_executor_job(
                    self._test_connection, host, DEFAULT_PORT
                )
            except Exception:
                _LOGGER.debug(
                    "Connection test failed for Luxtronik at %s:%d", host, DEFAULT_PORT
                )
                errors["base"] = "cannot_connect"
            else:
                # D-07: port and poll_interval stored in data, NOT shown in UI form
                return self.async_create_entry(
                    title=host,
                    data={
                        CONF_HOST: host,
                        "port": DEFAULT_PORT,
                        "poll_interval": DEFAULT_POLL_INTERVAL,
                    },
                )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({vol.Required(CONF_HOST): str}),
            errors=errors,
        )

    @staticmethod
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> "LuxtronikOptionsFlow":
        """Return the options flow handler for this integration.

        Called by HA when the user clicks "Configure" on the integration card
        in Settings > Devices & Services. Returns the options flow that lets
        users update host and poll_interval without removing the integration.

        Args:
            config_entry: The existing config entry to reconfigure.

        Returns:
            A LuxtronikOptionsFlow instance bound to the config entry.
        """
        return LuxtronikOptionsFlow(config_entry)

    @staticmethod
    def _test_connection(host: str, port: int) -> None:
        """Test connectivity to the Luxtronik 2.0 controller.

        Runs in the HA executor thread pool — blocking socket I/O is permitted here.

        Uses ``luxtronik.Luxtronik.__new__`` followed by manual attribute initialization
        to avoid the auto-read() call in ``Luxtronik.__init__``, then calls ``lux.read()``
        once to verify connectivity. This is the same pattern used in coordinator.py
        (ARCH-01) — see coordinator.py _sync_read() for the detailed rationale.

        Any exception (OSError, socket timeout, protocol error) propagates to the caller,
        which maps it to the ``cannot_connect`` error key (SETUP-03).

        Args:
            host: IP address or hostname of the Luxtronik 2.0 controller.
            port: TCP port of the Luxtronik binary protocol server (default 8889).

        Raises:
            Exception: Any network or protocol error raised by the luxtronik library.
        """
        # ARCH-01: Use __new__ to skip Luxtronik.__init__ auto-read.
        # Identical pattern to coordinator.py _sync_read() and luxtronik_client.py.
        lux = luxtronik.Luxtronik.__new__(luxtronik.Luxtronik)
        lux._host = host
        lux._port = port
        lux._socket = None
        lux.calculations = luxtronik.Calculations()
        lux.parameters = luxtronik.Parameters()
        lux.visibilities = luxtronik.Visibilities()
        lux.read()  # blocking — OK, running in executor thread


class LuxtronikOptionsFlow(config_entries.OptionsFlow):
    """Handle the Luxtronik 2 Modbus Proxy options flow.

    Allows users to reconfigure the heat pump IP address and poll interval
    from Settings > Devices & Services > Luxtronik 2 Modbus Proxy > Configure,
    without removing and re-adding the integration.

    On save, changes are persisted via async_update_entry into the config entry
    data dict. The update listener in __init__.py then triggers a full config
    entry reload so the coordinator reconnects with the new settings.
    """

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize the options flow with the existing config entry.

        Args:
            config_entry: The config entry being reconfigured. Used to pre-fill
                the form with the current host and poll_interval values.
        """
        self.config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        """Handle the options form step.

        Pre-fills the form with current values from the config entry. On
        submission, strips whitespace from host, runs a connection test if the
        host changed, persists the new values via async_update_entry, and
        returns async_create_entry to signal completion.

        Args:
            user_input: Form data supplied by HA's UI, or None on first render.

        Returns:
            A FlowResult — either show_form to re-render with errors, or
            async_create_entry to finish and trigger the update listener.
        """
        errors: dict[str, str] = {}

        current_host: str = self.config_entry.data[CONF_HOST]
        current_poll_interval: int = self.config_entry.options.get(
            "poll_interval",
            self.config_entry.data.get("poll_interval", DEFAULT_POLL_INTERVAL),
        )

        if user_input is not None:
            host: str = user_input[CONF_HOST].strip()
            poll_interval: int = user_input["poll_interval"]

            # Only test the connection if the host has changed.
            # Avoids unnecessary network I/O when the user only changes the interval.
            if host != current_host:
                try:
                    await self.hass.async_add_executor_job(
                        LuxtronikConfigFlow._test_connection, host, DEFAULT_PORT
                    )
                except Exception:
                    _LOGGER.debug(
                        "Options flow connection test failed for Luxtronik at %s:%d",
                        host,
                        DEFAULT_PORT,
                    )
                    errors["base"] = "cannot_connect"

            if not errors:
                # Persist both host and poll_interval into the config entry data dict.
                # The update listener in __init__.py will reload the entry so the
                # coordinator picks up the new values immediately.
                self.hass.config_entries.async_update_entry(
                    self.config_entry,
                    data={
                        **self.config_entry.data,
                        CONF_HOST: host,
                        "port": DEFAULT_PORT,
                        "poll_interval": poll_interval,
                    },
                )
                # Return empty options dict — all data is stored in entry.data above.
                return self.async_create_entry(title="", data={})

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_HOST, default=current_host): str,
                    vol.Required(
                        "poll_interval", default=current_poll_interval
                    ): vol.All(int, vol.Range(min=10, max=300)),
                }
            ),
            errors=errors,
        )
