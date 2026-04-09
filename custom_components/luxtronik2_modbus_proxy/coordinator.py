"""Coordinator for the Luxtronik 2 Modbus Proxy Home Assistant integration.

Implements a DataUpdateCoordinator that polls the Luxtronik 2.0 heat pump
controller using the connect-per-call pattern. Each poll cycle creates a new
luxtronik.Luxtronik instance, reads all data, extracts raw integer values, and
discards the instance — releasing the single TCP connection on port 8889 so that
other tools (e.g., the BenPru/luxtronik HA integration) can coexist.

Architecture constraints enforced here:
- ARCH-01: Connect-per-call pattern via ``luxtronik.Luxtronik.__new__`` to avoid
  the auto-read() call in Luxtronik.__init__.
- ARCH-02: All blocking luxtronik calls run via ``hass.async_add_executor_job``
  to avoid stalling the HA asyncio event loop.
- ARCH-03: A single ``asyncio.Lock`` serializes all read and write operations,
  enforcing the Luxtronik 2.0 single-connection constraint.
"""

from __future__ import annotations

import asyncio
from datetime import timedelta
import logging

import luxtronik

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DEFAULT_POLL_INTERVAL, DEFAULT_PORT, DOMAIN

_LOGGER = logging.getLogger(__name__)


class LuxtronikCoordinator(DataUpdateCoordinator[dict]):
    """Coordinator for Luxtronik 2.0 heat pump data.

    Implements the connect-per-call pattern: creates a new luxtronik.Luxtronik
    instance for each poll cycle and discards it after reading. This releases
    the single TCP connection on port 8889 between poll cycles, allowing the
    BenPru/luxtronik HA integration to coexist on the same controller. (ARCH-01)

    All luxtronik library calls run in the HA executor thread pool via
    ``hass.async_add_executor_job`` to avoid blocking the HA event loop. (ARCH-02)

    A single asyncio.Lock serializes all read and write operations to enforce
    the Luxtronik 2.0 single-connection constraint — only one TCP connection
    is permitted at any time. (ARCH-03)

    coordinator.data structure (D-05):
        {
            "parameters": dict[int, int],    # Luxtronik parameter index -> raw int value
            "calculations": dict[int, int],  # Luxtronik calculation index -> raw int value
        }
    """

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: ConfigEntry,
        host: str,
        port: int = DEFAULT_PORT,
    ) -> None:
        """Initialize the LuxtronikCoordinator.

        Args:
            hass: The Home Assistant instance.
            config_entry: The config entry this coordinator is associated with.
            host: Hostname or IP address of the Luxtronik 2.0 controller.
            port: TCP port of the Luxtronik binary protocol server (default 8889).
        """
        self._host = host
        self._port = port
        # ARCH-03: Single lock serializes all TCP access. Created here so Phase 7
        # write methods acquire the same lock without restructuring the coordinator.
        self._lock = asyncio.Lock()

        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            config_entry=config_entry,
            update_interval=timedelta(seconds=DEFAULT_POLL_INTERVAL),
        )

    async def _async_update_data(self) -> dict:
        """Fetch all data from the Luxtronik controller.

        Acquires the serialization lock (ARCH-03), then dispatches the blocking
        read to the executor thread pool (ARCH-02). Creates a fresh Luxtronik
        instance for each call (ARCH-01) and discards it after value extraction.

        Returns:
            A dict with keys ``"parameters"`` and ``"calculations"``, each mapping
            Luxtronik indices to raw integer values (D-05).

        Raises:
            UpdateFailed: On any exception from the luxtronik library or network,
                causing the coordinator to mark entities unavailable and triggering
                HA's built-in retry backoff.
        """
        async with self._lock:  # ARCH-03: serialize concurrent read/write access
            try:
                data = await self.hass.async_add_executor_job(self._sync_read)
            except Exception as err:
                raise UpdateFailed(
                    f"Error communicating with Luxtronik at {self._host}: {err}"
                ) from err
        return data

    def _sync_read(self) -> dict:
        """Read all parameters and calculations from the Luxtronik controller.

        Runs in the HA executor thread pool — blocking socket I/O is permitted here.

        Uses ``luxtronik.Luxtronik.__new__`` followed by manual attribute
        initialization to avoid the auto-read call in ``Luxtronik.__init__``.
        The ``Luxtronik`` constructor unconditionally calls ``self.read()`` as its
        last operation, which would block the executor thread before attributes are
        set. By using ``__new__``, we control exactly when the read occurs. (ARCH-01)

        After calling ``lux.read()``, extracts raw integer values for all
        parameters and calculations using ``to_heatpump()`` — the wire-format
        integers consumed by Modbus clients and HA entity platforms. (D-05)

        Returns:
            A dict matching the D-05 structure:
            ``{"parameters": dict[int, int], "calculations": dict[int, int]}``
        """
        # ARCH-01: Use __new__ to skip Luxtronik.__init__ auto-read.
        # Luxtronik.__init__ calls self.read() unconditionally with no opt-out.
        # This is the same pattern used in luxtronik_client.py (verified against
        # the live library via inspect.getsource).
        lux = luxtronik.Luxtronik.__new__(luxtronik.Luxtronik)
        lux._host = self._host
        lux._port = self._port
        lux._socket = None
        lux.calculations = luxtronik.Calculations()
        lux.parameters = luxtronik.Parameters()
        lux.visibilities = luxtronik.Visibilities()
        lux.read()  # blocking — OK, we are running in the executor thread

        # Extract raw integer values for all parameters (read/write Luxtronik params).
        # to_heatpump() converts the library's internal value back to the wire-format
        # integer (e.g., 200 for 20.0 degC, 2 for HeatingMode "Party").
        parameters: dict[int, int] = {}
        for idx, param in enumerate(lux.parameters.parameters):
            if param is not None:
                raw = param.to_heatpump(param.value)
                if raw is not None:
                    parameters[idx] = int(raw)

        # Extract raw integer values for all calculations (read-only Luxtronik data).
        calculations: dict[int, int] = {}
        for idx, calc in enumerate(lux.calculations.calculations):
            if calc is not None:
                raw = calc.to_heatpump(calc.value)
                if raw is not None:
                    calculations[idx] = int(raw)

        _LOGGER.debug(
            "Luxtronik read complete: %d parameters, %d calculations",
            len(parameters),
            len(calculations),
        )
        return {"parameters": parameters, "calculations": calculations}
