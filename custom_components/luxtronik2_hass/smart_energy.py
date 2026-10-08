"""Smart Energy manager for Luxtronik 2.0 heat pumps.

Provides two independent automation features for heat pumps with multi-layer
buffer tanks and domestic hot water (DHW) heat exchangers:

**Solar Boost**: When grid feed-in exceeds a configurable threshold, the hot
water setpoint is raised to harvest surplus solar energy into the buffer tank.
A configurable minimum runtime prevents rapid cycling during cloud cover.

**Night Heating Pause**: Disables floor heating during configurable night hours
to prevent the heating circuit from cooling down the buffer tank overnight,
ensuring hot water is available in the morning.

Both features are independently toggleable and fully configurable via HA
switch and number entities exposed by switch.py.

**Restart safety**: The boost/pause state lives only in memory. If Home
Assistant stops or crashes while a boost or pause is active, the controller
keeps the raised setpoint / heating OFF. On startup the manager therefore
reconciles with the values actually on the controller (see
``_reconcile_controller_state``) so a stale boost or pause is taken over and
ended by the normal evaluation instead of hanging until the next cycle.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, time, timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.event import (
    async_track_state_change_event,
    async_track_time_interval,
)

from .const import (
    DEFAULT_GRID_SENSOR,
    DEFAULT_NIGHT_PAUSE_ENABLED,
    DEFAULT_NIGHT_PAUSE_END,
    DEFAULT_NIGHT_PAUSE_START,
    DEFAULT_SOLAR_BOOST_ENABLED,
    DEFAULT_SOLAR_BOOST_TEMP,
    DEFAULT_SOLAR_MIN_RUNTIME,
    DEFAULT_SOLAR_NORMAL_TEMP,
    DEFAULT_SOLAR_THRESHOLD,
    HEATING_MODE_AUTO,
    HEATING_MODE_OFF,
    HOT_WATER_MODE_PARTY,
    PARAM_HEATING_MODE,
    PARAM_HOT_WATER_MODE,
    PARAM_HOT_WATER_SETPOINT,
    SOLAR_DEBOUNCE_SECONDS,
)
from .coordinator import LuxtronikCoordinator

_LOGGER = logging.getLogger(__name__)


class SmartEnergyManager:
    """Manages Solar Boost and Night Heating Pause automations.

    Instantiated once per config entry in __init__.py. Listens to grid sensor
    state changes and a periodic timer to evaluate conditions and write
    parameter changes to the heat pump via the coordinator.

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
        """Initialize the smart energy manager.

        Args:
            hass: The Home Assistant instance.
            coordinator: The LuxtronikCoordinator for parameter writes.
            entry: The config entry with smart energy settings.
        """
        self.hass = hass
        self.coordinator = coordinator
        self.entry = entry

        # Solar boost state
        self._boost_active = False
        self._boost_activated_at: datetime | None = None
        self._debounce_start: datetime | None = None

        # Night pause state
        self._night_pause_active = False

        # Unsub callbacks for cleanup
        self._unsub_grid_listener = None
        self._unsub_timer = None

        # ha-005: serialize evaluations so grid-change bursts and the 60 s timer
        # cannot stack unbounded tasks while a coordinator write is slow. A new
        # evaluation is DROPPED (not queued) while one is already in flight.
        self._eval_lock = asyncio.Lock()

    @property
    def solar_boost_enabled(self) -> bool:
        """Return whether solar boost is enabled."""
        return self.entry.data.get("solar_boost_enabled", DEFAULT_SOLAR_BOOST_ENABLED)

    @property
    def grid_sensor(self) -> str:
        """Return the grid sensor entity ID."""
        return self.entry.data.get("grid_sensor", DEFAULT_GRID_SENSOR)

    @property
    def solar_threshold(self) -> float:
        """Return the grid feed-in threshold in watts."""
        return self.entry.data.get("solar_threshold", DEFAULT_SOLAR_THRESHOLD)

    @property
    def solar_normal_temp(self) -> float:
        """Return the normal hot water setpoint in degrees C."""
        return self.entry.data.get("solar_normal_temp", DEFAULT_SOLAR_NORMAL_TEMP)

    @property
    def solar_boost_temp(self) -> float:
        """Return the boosted hot water setpoint in degrees C."""
        return self.entry.data.get("solar_boost_temp", DEFAULT_SOLAR_BOOST_TEMP)

    @property
    def solar_min_runtime(self) -> int:
        """Return the minimum boost runtime in minutes."""
        return self.entry.data.get("solar_min_runtime", DEFAULT_SOLAR_MIN_RUNTIME)

    @property
    def night_pause_enabled(self) -> bool:
        """Return whether night heating pause is enabled."""
        return self.entry.data.get(
            "night_pause_enabled", DEFAULT_NIGHT_PAUSE_ENABLED
        )

    @property
    def night_pause_start(self) -> time:
        """Return the night pause start time."""
        raw = self.entry.data.get("night_pause_start", DEFAULT_NIGHT_PAUSE_START)
        parts = str(raw).split(":")
        return time(int(parts[0]), int(parts[1]))

    @property
    def night_pause_end(self) -> time:
        """Return the night pause end time."""
        raw = self.entry.data.get("night_pause_end", DEFAULT_NIGHT_PAUSE_END)
        parts = str(raw).split(":")
        return time(int(parts[0]), int(parts[1]))

    @property
    def boost_active(self) -> bool:
        """Return whether solar boost is currently active."""
        return self._boost_active

    @property
    def night_pause_currently_active(self) -> bool:
        """Return whether night pause is currently suppressing heating."""
        return self._night_pause_active

    async def async_start(self) -> None:
        """Start listening for grid sensor changes and periodic evaluation.

        Called from __init__.py after the coordinator is set up.
        """
        # Take over a boost/pause left on the controller by a previous run
        self._reconcile_controller_state()

        # Listen to grid sensor state changes for solar boost
        if self.grid_sensor:
            self._unsub_grid_listener = async_track_state_change_event(
                self.hass, [self.grid_sensor], self._handle_grid_change
            )

        # Periodic evaluation every 60 seconds for night pause and boost timeout
        self._unsub_timer = async_track_time_interval(
            self.hass, self._periodic_evaluate, timedelta(seconds=60)
        )

        # Initial evaluation
        await self._evaluate_all()

        _LOGGER.info(
            "Smart Energy started — solar_boost=%s (sensor=%s, threshold=%dW), "
            "night_pause=%s (%s-%s)",
            self.solar_boost_enabled,
            self.grid_sensor or "not configured",
            self.solar_threshold,
            self.night_pause_enabled,
            self.night_pause_start,
            self.night_pause_end,
        )

    def _reconcile_controller_state(self) -> None:
        """Adopt a boost or pause that a previous run left on the controller.

        Without this, a restart during an active Solar Boost leaves the hot
        water setpoint at the boost temperature indefinitely: the in-memory
        flag is False after startup, so ``_evaluate_solar_boost`` never
        deactivates it. The same applies to a Night Heating Pause that ends
        while Home Assistant is down (heating would stay OFF).

        Only values that exactly match what this manager writes are adopted,
        and only while the feature is enabled, so manual settings stay
        untouched. An adopted boost counts as having passed its minimum
        runtime; the initial evaluation then ends it unless the surplus
        is still there.
        """
        params = (self.coordinator.data or {}).get("parameters", {})

        boost_raw = int(self.solar_boost_temp * 10)
        if (
            self.solar_boost_enabled
            and boost_raw != int(self.solar_normal_temp * 10)
            and params.get(PARAM_HOT_WATER_SETPOINT) == boost_raw
            # Party mode means Bath Boost owns the setpoint (it cleans up itself)
            and params.get(PARAM_HOT_WATER_MODE) != HOT_WATER_MODE_PARTY
        ):
            _LOGGER.warning(
                "Hot water setpoint is still at the solar boost value %.1f°C "
                "from a previous run — taking over the boost",
                self.solar_boost_temp,
            )
            self._boost_active = True
            self._boost_activated_at = datetime.now() - timedelta(
                minutes=self.solar_min_runtime
            )

        if (
            self.night_pause_enabled
            and params.get(PARAM_HEATING_MODE) == HEATING_MODE_OFF
        ):
            _LOGGER.info(
                "Heating mode is OFF on startup — treating it as an active "
                "night heating pause"
            )
            self._night_pause_active = True

    async def async_stop(self) -> None:
        """Stop all listeners and restore normal parameters.

        Called on config entry unload and on Home Assistant shutdown
        (EVENT_HOMEASSISTANT_STOP, registered in __init__.py). Safe to call
        more than once.
        """
        if self._unsub_grid_listener:
            self._unsub_grid_listener()
            self._unsub_grid_listener = None
        if self._unsub_timer:
            self._unsub_timer()
            self._unsub_timer = None

        # Restore normal values if boost was active
        if self._boost_active:
            await self._set_hot_water_temp(self.solar_normal_temp)
            self._boost_active = False

        # Restore heating if night pause was active
        if self._night_pause_active:
            await self._set_heating_mode(HEATING_MODE_AUTO)
            self._night_pause_active = False

    @callback
    def _handle_grid_change(self, event) -> None:
        """Handle grid sensor state changes."""
        self.hass.async_create_task(self._guarded_evaluate(solar_only=True))

    @callback
    def _periodic_evaluate(self, now=None) -> None:
        """Periodically evaluate night pause and boost timeout."""
        self.hass.async_create_task(self._guarded_evaluate())

    async def _guarded_evaluate(self, solar_only: bool = False) -> None:
        """Run an evaluation unless one is already in flight.

        ha-005: without this guard, every grid-sensor change plus the 60 s timer
        spawned a fresh task; when a coordinator write hung, those tasks piled up
        (~900 observed overnight). ``asyncio.Lock.locked()`` and the immediate
        ``async with`` acquire run without an intervening await, so the first
        task acquires the lock and all concurrent ones see it locked and drop.
        """
        if self._eval_lock.locked():
            _LOGGER.debug("Smart Energy evaluation already running — dropping this one")
            return
        async with self._eval_lock:
            if solar_only:
                await self._evaluate_solar_boost()
            else:
                await self._evaluate_all()

    async def _evaluate_all(self) -> None:
        """Evaluate both features."""
        await self._evaluate_solar_boost()
        await self._evaluate_night_pause()

    async def _evaluate_solar_boost(self) -> None:
        """Evaluate whether to activate or deactivate solar boost.

        Grid sensor convention: positive = consumption, negative = feed-in.
        Boost activates when feed-in exceeds threshold (grid_power < -threshold).
        Deactivates only after minimum runtime has elapsed.
        """
        if not self.solar_boost_enabled or not self.grid_sensor:
            if self._boost_active:
                await self._deactivate_boost()
            return

        # Read grid sensor value (positive = consumption, negative = feed-in)
        state = self.hass.states.get(self.grid_sensor)
        if state is None or state.state in ("unknown", "unavailable"):
            return

        try:
            grid_power = float(state.state)
        except (ValueError, TypeError):
            return

        now = datetime.now()

        # Negative grid_power means feeding into the grid.
        # Boost when feed-in exceeds threshold: e.g. grid=-2000W, threshold=1500 → -2000 < -1500 → True
        if grid_power < -self.solar_threshold:
            # Feed-in exceeds threshold — activate boost if not already active
            if not self._boost_active:
                if self._debounce_start is None:
                    self._debounce_start = now
                    _LOGGER.debug("Solar boost debounce started")
                else:
                    elapsed = (now - self._debounce_start).total_seconds()
                    if elapsed >= SOLAR_DEBOUNCE_SECONDS:
                        self._debounce_start = None
                        await self._activate_boost()
                    else:
                        _LOGGER.debug(
                            "Solar boost debounce: %.0fs remaining",
                            SOLAR_DEBOUNCE_SECONDS - elapsed,
                        )
        else:
            # Feed-in dropped below threshold — reset debounce timer
            self._debounce_start = None
            # Below threshold (consuming or not enough feed-in) — deactivate only if min runtime elapsed
            if self._boost_active and self._boost_activated_at:
                elapsed = (now - self._boost_activated_at).total_seconds() / 60
                if elapsed >= self.solar_min_runtime:
                    await self._deactivate_boost()
                else:
                    _LOGGER.debug(
                        "Solar boost min runtime not elapsed (%.0f/%.0f min)",
                        elapsed,
                        self.solar_min_runtime,
                    )

    async def _activate_boost(self) -> None:
        """Activate solar boost — raise hot water setpoint.

        ha-005: state is set BEFORE the write. If the write hangs or fails, the
        manager still regards the boost as active, so the next evaluation runs
        the normal deactivation path instead of re-issuing an activation write
        on top of a possibly-pending one.
        """
        _LOGGER.info(
            "Solar boost ACTIVATING — setting hot water to %.1f°C",
            self.solar_boost_temp,
        )
        self._boost_active = True
        self._boost_activated_at = datetime.now()
        await self._set_hot_water_temp(self.solar_boost_temp)

    async def _deactivate_boost(self) -> None:
        """Deactivate solar boost — restore normal hot water setpoint.

        ha-005: state is cleared BEFORE the write (see _activate_boost).
        """
        _LOGGER.info(
            "Solar boost DEACTIVATING — setting hot water to %.1f°C",
            self.solar_normal_temp,
        )
        self._boost_active = False
        self._boost_activated_at = None
        await self._set_hot_water_temp(self.solar_normal_temp)

    async def _evaluate_night_pause(self) -> None:
        """Evaluate whether to activate or deactivate night heating pause.

        During the configured night window, sets heating mode to OFF.
        Outside the window, restores heating mode to AUTO.
        """
        if not self.night_pause_enabled:
            if self._night_pause_active:
                await self._set_heating_mode(HEATING_MODE_AUTO)
                self._night_pause_active = False
            return

        now = datetime.now().time()
        in_night_window = self._is_in_night_window(now)

        if in_night_window and not self._night_pause_active:
            _LOGGER.info("Night heating pause ACTIVATING — setting heating to OFF")
            # ha-005: set state before the write (see _activate_boost).
            self._night_pause_active = True
            await self._set_heating_mode(HEATING_MODE_OFF)
        elif not in_night_window and self._night_pause_active:
            _LOGGER.info("Night heating pause DEACTIVATING — setting heating to AUTO")
            self._night_pause_active = False
            await self._set_heating_mode(HEATING_MODE_AUTO)

    def _is_in_night_window(self, now: time) -> bool:
        """Check if the current time is within the night pause window.

        Handles overnight windows correctly (e.g. 18:00-09:00 spans midnight).
        """
        start = self.night_pause_start
        end = self.night_pause_end
        if start <= end:
            # Same-day window (e.g. 22:00-23:00)
            return start <= now < end
        # Overnight window (e.g. 18:00-09:00)
        return now >= start or now < end

    async def _set_hot_water_temp(self, temp: float) -> None:
        """Write hot water setpoint to the controller."""
        raw = int(temp * 10)
        try:
            await self.coordinator.async_write_parameter(
                PARAM_HOT_WATER_SETPOINT, raw
            )
        except Exception:
            _LOGGER.exception("Failed to write hot water setpoint %.1f°C", temp)

    async def _set_heating_mode(self, mode: int) -> None:
        """Write heating mode to the controller."""
        try:
            await self.coordinator.async_write_parameter(PARAM_HEATING_MODE, mode)
        except Exception:
            _LOGGER.exception("Failed to write heating mode %d", mode)
