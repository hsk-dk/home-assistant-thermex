"""Thermex Fan entity with discrete presets and persistent runtime tracking."""
import logging
from collections.abc import Callable
from datetime import datetime
from typing import Any

from homeassistant.components.fan import FanEntity, FanEntityFeature
from homeassistant.core import callback
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers.dispatcher import (
    async_dispatcher_send,
)
from homeassistant.helpers.event import async_call_later
from homeassistant.util.percentage import (
    ordered_list_item_to_percentage,
    percentage_to_ordered_list_item,
)

from .const import (
    DELAYED_TURNOFF_COUNTDOWN_INTERVAL,
    DOMAIN,
    FALLBACK_STATUS_TIMEOUT,
)
from .data import ThermexConfigEntry
from .entity import ThermexEntity
from .hub import ThermexHub
from .runtime_manager import RuntimeManager

_LOGGER = logging.getLogger(__name__)

PARALLEL_UPDATES = 1

# The four levels of the hood (the remote shows the same four). "off" is not a
# preset. They are also the fan's speeds (25/50/75/100 %): the presets are kept
# on purpose so existing automations and the familiar names keep working.
PRESET_MODES = ["low", "medium", "high", "boost"]
_MODE_TO_VALUE = {"off": 0, "low": 1, "medium": 2, "high": 3, "boost": 4}
_VALUE_TO_MODE = {v: k for k, v in _MODE_TO_VALUE.items()}


async def async_setup_entry(hass, entry: ThermexConfigEntry, async_add_entities) -> None:
    """Set up the Thermex fan with runtime storage."""
    hub = entry.runtime_data.hub
    runtime_manager = entry.runtime_data.runtime_manager
    fan_entity = ThermexFan(hub, runtime_manager, entry)
    async_add_entities([fan_entity])


class ThermexFan(ThermexEntity, FanEntity):
    """Thermex extractor fan with presets and runtime tracking."""

    _attr_supported_features = (
        FanEntityFeature.PRESET_MODE
        | FanEntityFeature.TURN_ON
        | FanEntityFeature.TURN_OFF
        | FanEntityFeature.SET_SPEED  # Enable percentage control
    )
    _attr_preset_modes = PRESET_MODES
    _attr_speed_count = 4  # 4 speeds: low(25%), medium(50%), high(75%), boost(100%)
    # Slow or noisy values: keep them in the state but out of the recorder
    _unrecorded_attributes = frozenset({
        "runtime_hours", "filter_time", "last_reset", "threshold", "alert",
        "delayed_off_remaining", "delayed_off_scheduled_time",
    })

    def __init__(self, hub: ThermexHub, runtime_manager: RuntimeManager, entry):
        super().__init__(hub)
        self._runtime_manager = runtime_manager
        self._entry = entry
        self._auto_off_handle: Callable[[], None] | None = None
        self._delayed_off_handle: Callable[[], None] | None = None
        self._countdown_handle: Callable[[], None] | None = None
        self._delayed_off_active = False
        self._delayed_off_remaining = 0
        self._delayed_off_scheduled_time: datetime | None = None
        self._attr_translation_key = "thermex_fan"
        self._attr_name = None  # main entity: named after the device
        self._attr_unique_id = f"{hub.unique_id}_fan"

        # State
        self._is_on = False
        self._preset_mode = self._runtime_manager.get_last_preset()
        # What "turn on" without arguments switches to (the last level in use)
        last = self._preset_mode
        self._last_active_preset = last if last in PRESET_MODES else "medium"
        self._got_initial_state = False

    @property
    def is_on(self) -> bool:
        return self._is_on

    @property
    def preset_mode(self) -> str | None:
        """The active level, or None when the fan is off."""
        if not self._is_on or self._preset_mode not in PRESET_MODES:
            return None
        return self._preset_mode

    @property
    def percentage(self) -> int | None:
        """Return the current speed percentage (0 when off)."""
        if self.preset_mode is None:
            return 0
        return ordered_list_item_to_percentage(PRESET_MODES, self._preset_mode)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        
        # Get current options from config entry
        current_options = self._entry.options
        
        attributes = {
            "runtime_hours": self._runtime_manager.get_runtime_hours(),
            "filter_time": self._runtime_manager.get_filter_time(),
            "last_reset": self._runtime_manager.get_last_reset() or "never",
            "threshold": current_options.get("fan_alert_hours", 30),
            "alert": self._runtime_manager.get_runtime_hours() >= current_options.get("fan_alert_hours", 30),
            # Delayed turn-off attributes
            "delayed_off_active": self._delayed_off_active,
            "delayed_off_remaining": self._delayed_off_remaining,
            "delayed_off_delay": current_options.get("fan_auto_off_delay", 10),
        }
        
        # Add scheduled time if active
        if self._delayed_off_scheduled_time:
            attributes["delayed_off_scheduled_time"] = self._delayed_off_scheduled_time.isoformat()
        
        return attributes

    async def async_added_to_hass(self) -> None:
        """Called when entity is added to hass."""
        _LOGGER.info("ThermexFan entity added to hass: %s", self.entity_id)
        await super().async_added_to_hass()
        _LOGGER.debug("ThermexFan: awaiting initial notify for state")
        self.async_on_remove(
            async_call_later(self.hass, FALLBACK_STATUS_TIMEOUT, self._fallback_status)
        )

    @callback
    def _handle_notify(self, ntf_type: str, data: dict) -> None:
        """Handle incoming fan notifications and update runtime/state."""
        if ntf_type.lower() != "fan":
            return

        fan = data.get("Fan", {})
        new_speed = fan.get("fanspeed", 0)
        new_on = bool(fan.get("fanonoff", 0)) and new_speed != 0
        new_mode = _VALUE_TO_MODE.get(new_speed, "off")

        # Only touch storage when something actually changed: every 30 s
        # heartbeat delivers a full Status and must not rewrite the file.
        changed = False

        # turned on?
        if new_on and not self._is_on:
            self._runtime_manager.start()
            changed = True

        # turned off?
        if not new_on and self._is_on:
            self._runtime_manager.stop()
            changed = True

        # always record last_reset on first on
        if new_on and self._runtime_manager.get_last_reset() is None:
            self._runtime_manager.reset()
            changed = True

        if new_mode != self._runtime_manager.get_last_preset():
            self._runtime_manager.set_last_preset(new_mode)
            changed = True

        # update local state
        self._is_on = new_on
        self._preset_mode = new_mode
        if new_on and new_mode in PRESET_MODES:
            self._last_active_preset = new_mode

        if changed:
            self.hass.async_create_task(self._runtime_manager.save())

        self._got_initial_state = True  # Mark that we've received initial state
        self.schedule_update_ha_state()

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        speed = _MODE_TO_VALUE[preset_mode]

        # The state (and runtime tracking) is updated from the Status read-back
        # that send_update triggers, see _handle_notify.
        await self._hub.send_update(
            {"Fan": {"fanonoff": int(speed > 0), "fanspeed": speed}},
        )

    async def async_set_percentage(self, percentage: int) -> None:
        """Set the fan speed by percentage, mapping to discrete preset modes."""
        if percentage == 0:
            await self.async_turn_off()
            return

        # Map percentage ranges to preset modes:
        # 1-25%   -> low
        # 26-50%  -> medium
        # 51-75%  -> high
        # 76-100% -> boost
        preset = percentage_to_ordered_list_item(PRESET_MODES, percentage)

        await self.async_set_preset_mode(preset)

    async def async_turn_on(self, percentage=None, preset_mode=None, **kwargs) -> None:
        if percentage is not None:
            await self.async_set_percentage(percentage)
        elif preset_mode:
            await self.async_set_preset_mode(preset_mode)
        else:
            await self.async_set_preset_mode(self._last_active_preset)

    async def async_turn_off(self, **kwargs) -> None:
        await self.cancel_delayed_off()  # Cancel any delayed turn-off
        await self.async_set_preset_mode("off")

    async def async_reset(self, **kwargs) -> None:
        self._runtime_manager.reset()
        await self._runtime_manager.save()
        self.schedule_update_ha_state()

    async def start_delayed_off(self) -> None:
        """Start the delayed turn-off timer."""
        _LOGGER.info("start_delayed_off service called")
        
        if not self._is_on:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="fan_not_running",
            )

        # Cancel any existing delayed turn-off
        await self.cancel_delayed_off()

        # Get delay from config entry options
        current_options = self._entry.options
        delay_minutes = max(1, min(120, current_options.get("fan_auto_off_delay", 10)))
        
        _LOGGER.info("Starting delayed turn-off in %d minutes", delay_minutes)
        
        self._delayed_off_active = True
        self._delayed_off_remaining = delay_minutes
        
        # Calculate scheduled time
        from datetime import timedelta

        from homeassistant.util import dt as dt_util
        
        self._delayed_off_scheduled_time = dt_util.now() + timedelta(minutes=delay_minutes)

        scheduled_time_str = self._delayed_off_scheduled_time.strftime("%H:%M") if self._delayed_off_scheduled_time else "unknown"
        _LOGGER.info("Starting delayed turn-off: %d minutes (until %s)", delay_minutes, scheduled_time_str)
        _LOGGER.debug("Delayed turn-off details: active=%s, remaining=%d, handle=%s", self._delayed_off_active, self._delayed_off_remaining, self._delayed_off_handle is not None)
        
        # Schedule the turn-off
        self._delayed_off_handle = async_call_later(
            self.hass, delay_minutes * 60, self._handle_delayed_off
        )
        
        _LOGGER.debug("Delayed turn-off scheduled: handle=%s, seconds=%d", self._delayed_off_handle is not None, delay_minutes * 60)
        
        # Start countdown timer (update every minute)
        self._countdown_handle = async_call_later(
            self.hass, DELAYED_TURNOFF_COUNTDOWN_INTERVAL, self._update_countdown
        )
        
        self.schedule_update_ha_state()
        
        # Notify other entities about delayed turn-off activation
        scheduled_iso = self._delayed_off_scheduled_time.isoformat() if self._delayed_off_scheduled_time else None
        async_dispatcher_send(
            self.hass,
            self._hub.signal,
            "delayed_turn_off",
            {
                "active": True, 
                "scheduled_time": scheduled_iso,
                "remaining": delay_minutes
            },
        )

    async def cancel_delayed_off(self) -> None:
        """Cancel the delayed turn-off timer."""
        if self._delayed_off_handle:
            self._delayed_off_handle()
            self._delayed_off_handle = None
        # Also stop the countdown chain, otherwise a later restart runs two of them
        if self._countdown_handle:
            self._countdown_handle()
            self._countdown_handle = None

        self._delayed_off_active = False
        self._delayed_off_remaining = 0
        self._delayed_off_scheduled_time = None
        self.schedule_update_ha_state()
        _LOGGER.info("Delayed turn-off cancelled")
        
        # Notify other entities about delayed turn-off status change
        async_dispatcher_send(
            self.hass,
            self._hub.signal,
            "delayed_turn_off",
            {"active": False, "scheduled_time": None},
        )

    def _update_countdown(self, _now=None) -> None:
        """Update the countdown timer display."""
        self._countdown_handle = None
        if not self._delayed_off_active:
            return

        # Decrement the remaining time
        if self._delayed_off_remaining > 0:
            self._delayed_off_remaining -= 1
            self.schedule_update_ha_state()
            
            # Schedule next update in 1 minute if still active
            if self._delayed_off_remaining > 0:
                self._countdown_handle = async_call_later(
                    self.hass, DELAYED_TURNOFF_COUNTDOWN_INTERVAL, self._update_countdown
                )

    async def _handle_delayed_off(self, _now) -> None:
        """Handle the delayed turn-off event."""
        _LOGGER.info("Executing delayed turn-off - fan should turn off now")
        _LOGGER.debug("Current fan state before turn-off: is_on=%s, preset=%s", self._is_on, self._preset_mode)
        
        # Clear delayed turn-off state first
        self._delayed_off_handle = None
        if self._countdown_handle:
            self._countdown_handle()
            self._countdown_handle = None
        self._delayed_off_active = False
        self._delayed_off_remaining = 0
        self._delayed_off_scheduled_time = None
        
        # Turn off the fan
        await self.async_turn_off()
        
        _LOGGER.debug("Fan state after turn-off command: is_on=%s, preset=%s", self._is_on, self._preset_mode)
        _LOGGER.info("Delayed turn-off completed and state cleared")
        
        # Update the state immediately
        self.schedule_update_ha_state()
        
        # Notify other entities about delayed turn-off completion
        async_dispatcher_send(
            self.hass,
            self._hub.signal,
            "delayed_turn_off",
            {"active": False, "scheduled_time": None},
        )

    async def async_will_remove_from_hass(self) -> None:
        """Cancel any pending timers when entity is removed."""
        await self.cancel_delayed_off()

    async def _fallback_status(self, _now):
        if self._got_initial_state:
            return
        
        # Check if hub startup is complete - if so, we should have received initial status
        if self._hub.startup_complete:
            _LOGGER.debug("ThermexFan: Hub startup complete but no notify received, using default state")
            self._got_initial_state = True
            return
            
        _LOGGER.warning("ThermexFan: no notify received in 15s, fetching fallback status")
        try:
            data = await self._hub.request_fallback_status("ThermexFan")
            fan = data.get("Fan", {})
            if fan:
                self._is_on = bool(fan.get("fanonoff", 0)) and fan.get("fanspeed", 0) != 0
                self._preset_mode = _VALUE_TO_MODE.get(fan.get("fanspeed", 0), "off")
                self._runtime_manager.set_last_preset(self._preset_mode)
                self._got_initial_state = True
                self.schedule_update_ha_state()
            else:
                _LOGGER.debug("ThermexFan: No fan data in fallback response, using defaults")
                self._got_initial_state = True
        except Exception as err:
            _LOGGER.error("ThermexFan: fallback status failed: %s", err)
            # Set initial state anyway to avoid repeated warnings
            self._got_initial_state = True
