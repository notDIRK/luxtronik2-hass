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
