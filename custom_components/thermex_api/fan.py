"""Thermex Fan entity with discrete presets and persistent runtime tracking."""
import logging
from typing import Any, Optional, Callable
from datetime import datetime

from homeassistant.components.fan import FanEntity, FanEntityFeature
from homeassistant.core import callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect, async_dispatcher_send
from homeassistant.helpers import entity_platform
from homeassistant.helpers.event import async_call_later

from .hub import ThermexHub
from .const import DOMAIN, THERMEX_NOTIFY, FALLBACK_STATUS_TIMEOUT, DELAYED_TURNOFF_COUNTDOWN_INTERVAL
from .runtime_manager import RuntimeManager
from .delayed_off_helper import DelayedOffHelper

_LOGGER = logging.getLogger(__name__)

PRESET_MODES = ["off", "low", "medium", "high", "boost"]
_MODE_TO_VALUE = {"off": 0, "low": 1, "medium": 2, "high": 3, "boost": 4}
_VALUE_TO_MODE = {v: k for k, v in _MODE_TO_VALUE.items()}


async def async_setup_entry(hass, entry, async_add_entities) -> None:
    """Set up the Thermex fan with runtime storage."""
    entry_data = hass.data[DOMAIN][entry.entry_id]
    hub = entry_data.get("hub")
    runtime_manager = entry_data.get("runtime_manager")
    
    if not hub or not runtime_manager:
        _LOGGER.error("Missing hub or runtime_manager in entry data")
        return
    fan_entity = ThermexFan(hub, runtime_manager, entry)
    async_add_entities([fan_entity], update_before_add=True)

    # Register entity services
    platform = entity_platform.async_get_current_platform()
    platform.async_register_entity_service(
        "reset_runtime",
        {},
        "async_reset"
    )
    platform.async_register_entity_service(
        "start_delayed_off",
        {},
        "start_delayed_off"
    )
    platform.async_register_entity_service(
        "cancel_delayed_off",
        {},
        "cancel_delayed_off"
    )


class ThermexFan(FanEntity):
    """Thermex extractor fan with presets and runtime tracking."""

    _attr_supported_features = (
        FanEntityFeature.PRESET_MODE
        | FanEntityFeature.TURN_ON
        | FanEntityFeature.TURN_OFF
        | FanEntityFeature.SET_SPEED  # Enable percentage control
    )
    _attr_preset_modes = PRESET_MODES
    _attr_speed_count = 4  # 4 speeds: low(25%), medium(50%), high(75%), boost(100%)

    def __init__(self, hub: ThermexHub, runtime_manager: RuntimeManager, entry):
        self._hub = hub
        self._runtime_manager = runtime_manager
        self._entry = entry
        self._auto_off_handle: Optional[Callable[[], None]] = None
        self._unsub: Optional[Callable[[], None]] = None
        self._attr_translation_key = "thermex_fan"
        self._attr_has_entity_name = True
        self._attr_unique_id = f"{hub.unique_id}_fan"
        self._attr_icon = "mdi:fan"
        self._attr_device_info = hub.device_info

        # State
        self._is_on = False
        self._preset_mode = self._runtime_manager.get_last_preset()
        self._got_initial_state = False
        self._cached_hub_data: dict[str, Any] = {}  # Cache hub data to avoid repeated calls

    @property
    def is_on(self) -> bool:
        return self._is_on

    @property
    def preset_mode(self) -> str | None:
        return self._preset_mode

    @property
    def percentage(self) -> int | None:
        """Return the current speed percentage."""
        if not self._is_on or self._preset_mode == "off":
            return 0
        # Map preset modes to percentage:
        # low=25%, medium=50%, high=75%, boost=100%
        percentage_map = {
            "off": 0,
            "low": 25,
            "medium": 50,
            "high": 75,
            "boost": 100,
        }
        return percentage_map.get(self._preset_mode, 0)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        # Use cached hub data (updated during state changes)
        hub_data = self._cached_hub_data if self._cached_hub_data else self._hub.get_coordinator_data()
        
        # Get current options from config entry
        current_options = self._entry.options
        
        attributes = {
            "runtime_hours": self._runtime_manager.get_runtime_hours(),
            "filter_time": self._runtime_manager.get_filter_time(),
            "last_reset": self._runtime_manager.get_last_reset() or "never",
            "last_preset": self._runtime_manager.get_last_preset(),
            "threshold": current_options.get("fan_alert_hours", 30),
            "alert": self._runtime_manager.get_runtime_hours() >= current_options.get("fan_alert_hours", 30),
            "is_on": self._is_on,
            # Connection status attributes
            "connection_state": hub_data.get("connection_state", "unknown"),
            "last_error": hub_data.get("last_error"),
            "watchdog_active": hub_data.get("watchdog_active", False),
            "time_since_activity": hub_data.get("time_since_activity", 0),
            "heartbeat_interval": hub_data.get("heartbeat_interval", 30),
            "connection_timeout": hub_data.get("connection_timeout", 120),
            # Delayed turn-off delay setting
            "delayed_off_delay": current_options.get("fan_auto_off_delay", 10),
        }
        
        # Add delayed turn-off attributes from helper if initialized
        if hasattr(self, "_delayed_off_helper"):
            attributes.update(self._delayed_off_helper.get_state_attributes())
        
        return attributes

    async def async_added_to_hass(self) -> None:
        """Called when entity is added to hass."""
        _LOGGER.info("ThermexFan entity added to hass: %s", self.entity_id)
        self._delayed_off_helper = DelayedOffHelper(self.hass, self)
        self._unsub = async_dispatcher_connect(self.hass, THERMEX_NOTIFY, self._handle_notify)
        _LOGGER.debug("ThermexFan: awaiting initial notify for state")
        # Use a longer timeout and check if startup is complete
        async_call_later(self.hass, FALLBACK_STATUS_TIMEOUT, self._fallback_status)

    @callback
    def _handle_notify(self, ntf_type: str, data: dict) -> None:
        """Handle incoming fan notifications and update runtime/state."""
        if ntf_type.lower() != "fan":
            return

        fan = data.get("Fan", {})
        new_speed = fan.get("fanspeed", 0)
        new_on = bool(fan.get("fanonoff", 0)) and new_speed != 0
        new_mode = _VALUE_TO_MODE.get(new_speed, "off")

        # turned on?
        if new_on and not self._is_on:
            self._runtime_manager.start()
            self.hass.async_create_task(self._runtime_manager.save())

        # turned off?
        if not new_on and self._is_on:
            self._runtime_manager.stop()
            self.hass.async_create_task(self._runtime_manager.save())

        # always record last_reset on first on
        if new_on and self._runtime_manager.get_last_reset() is None:
            self._runtime_manager.reset()
            self.hass.async_create_task(self._runtime_manager.save())

        # update local state
        self._is_on = new_on
        self._preset_mode = new_mode
        self._runtime_manager.set_last_preset(new_mode)

        self.hass.async_create_task(self._runtime_manager.save())

        self._got_initial_state = True  # Mark that we've received initial state
        # Update cached hub data to avoid repeated calls in extra_state_attributes
        self._cached_hub_data = self._hub.get_coordinator_data()
        self.schedule_update_ha_state()

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        speed = _MODE_TO_VALUE[preset_mode]
        await self._hub.send_request("Update", {"Fan": {"fanonoff": int(speed > 0), "fanspeed": speed}})

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
        if percentage <= 25:
            preset = "low"
        elif percentage <= 50:
            preset = "medium"
        elif percentage <= 75:
            preset = "high"
        else:
            preset = "boost"
        
        await self.async_set_preset_mode(preset)
        self._runtime_manager.start()
        self._runtime_manager.set_last_preset(preset)
        await self._runtime_manager.save()
        # State will be updated via notify signal from hub

    async def async_turn_on(self, percentage=None, preset_mode=None, **kwargs) -> None:
        if percentage is not None:
            # Use percentage control
            await self.async_set_percentage(percentage)
        elif preset_mode:
            mode = preset_mode
            await self.async_set_preset_mode(mode)
            self._runtime_manager.start()
            self._runtime_manager.set_last_preset(mode)
            await self._runtime_manager.save()
            # State will be updated via notify signal from hub
        elif self._preset_mode and self._preset_mode != "off":
            mode = self._preset_mode
            await self.async_set_preset_mode(mode)
            self._runtime_manager.start()
            self._runtime_manager.set_last_preset(mode)
            await self._runtime_manager.save()
            # State will be updated via notify signal from hub
        else:
            mode = "medium"
            await self.async_set_preset_mode(mode)
            self._runtime_manager.start()
            self._runtime_manager.set_last_preset(mode)
            await self._runtime_manager.save()
            # State will be updated via notify signal from hub

    async def async_turn_off(self, **kwargs) -> None:
        await self.cancel_delayed_off()  # Cancel any delayed turn-off
        await self.async_set_preset_mode("off")
        self._runtime_manager.stop()
        self._runtime_manager.set_last_preset("off")
        await self._runtime_manager.save()
        # State will be updated via notify signal from hub

    async def async_reset(self, **kwargs) -> None:
        self._runtime_manager.reset()
        await self._runtime_manager.save()
        self.schedule_update_ha_state()

    async def start_delayed_off(self) -> None:
        """Start the delayed turn-off timer."""
        _LOGGER.info("start_delayed_off service called")
        
        # Get delay from config entry options
        current_options = self._entry.options
        delay_minutes = max(1, min(120, current_options.get("fan_auto_off_delay", 10)))
        
        success = await self._delayed_off_helper.start(delay_minutes)
        if success:
            self.schedule_update_ha_state()

    async def cancel_delayed_off(self) -> None:
        """Cancel the delayed turn-off timer."""
        await self._delayed_off_helper.cancel()
        self.schedule_update_ha_state()

    async def async_will_remove_from_hass(self) -> None:
        """Cancel any pending timers when entity is removed."""
        if self._unsub:
            self._unsub()
        if hasattr(self, "_delayed_off_helper"):
            await self._delayed_off_helper.cleanup()

    async def _handle_auto_off(self, _now) -> None:
        self._auto_off_handle = None
        _LOGGER.info("Auto turning off fan after timeout")
        await self.async_turn_off()
        self.async_write_ha_state()
    
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
