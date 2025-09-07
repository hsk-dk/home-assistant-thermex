"""Thermex Fan entity with discrete presets and persistent runtime tracking."""
import logging
from datetime import datetime, timedelta

from homeassistant.components.fan import FanEntity, FanEntityFeature
from homeassistant.core import callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect, async_dispatcher_send
from homeassistant.helpers import entity_platform
from homeassistant.helpers.storage import Store
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.util.dt import utcnow
from homeassistant.helpers.event import async_call_later

from .hub import ThermexHub
from .const import DOMAIN, THERMEX_NOTIFY, STORAGE_VERSION, RUNTIME_STORAGE_FILE
from .runtime_manager import RuntimeManager

_LOGGER = logging.getLogger(__name__)

PRESET_MODES = ["off", "low", "medium", "high", "boost"]
_MODE_TO_VALUE = {"off": 0, "low": 1, "medium": 2, "high": 3, "boost": 4}
_VALUE_TO_MODE = {v: k for k, v in _MODE_TO_VALUE.items()}


async def async_setup_entry(hass, entry, async_add_entities):
    """Set up the Thermex fan with runtime storage."""
    #hub: ThermexHub = hass.data[DOMAIN][entry.entry_id]
    entry_data = hass.data[DOMAIN][entry.entry_id]
    hub = entry_data["hub"]
    runtime_manager = entry_data["runtime_manager"]
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
    
    # Also register as domain services for easier access
    async def handle_start_delayed_off(call):
        """Handle start delayed off service call."""
        entity_id = call.data.get("entity_id")
        if entity_id:
            # Find the fan entity and call its method
            if entity_id == fan_entity.entity_id:
                await fan_entity.start_delayed_off()
        else:
            # No entity_id specified, call on our fan
            await fan_entity.start_delayed_off()
    
    async def handle_cancel_delayed_off(call):
        """Handle cancel delayed off service call."""
        entity_id = call.data.get("entity_id")
        if entity_id:
            if entity_id == fan_entity.entity_id:
                await fan_entity.cancel_delayed_off()
        else:
            await fan_entity.cancel_delayed_off()
    
    # Register the domain services
    hass.services.async_register(
        DOMAIN, 
        "start_delayed_off_domain", 
        handle_start_delayed_off
    )
    hass.services.async_register(
        DOMAIN, 
        "cancel_delayed_off_domain", 
        handle_cancel_delayed_off
    )


class ThermexFan(FanEntity):
    """Thermex extractor fan with presets and runtime tracking."""

    _attr_supported_features = (
        FanEntityFeature.PRESET_MODE
        | FanEntityFeature.TURN_ON
        | FanEntityFeature.TURN_OFF
    )
    _attr_preset_modes = PRESET_MODES

    def __init__(self, hub: ThermexHub, runtime_manager: RuntimeManager, entry):
        self._hub = hub
        self._runtime_manager = runtime_manager
        self._entry = entry
        self._auto_off_handle = None
        self._delayed_off_handle = None
        self._delayed_off_active = False
        self._delayed_off_remaining = 0
        self._delayed_off_scheduled_time = None
        self._unsub = None
        self._attr_translation_key = "thermex_fan"
        self._attr_has_entity_name = True
        self._attr_unique_id = f"{hub.unique_id}_fan"
        self._attr_icon = "mdi:fan"
        self._attr_device_info = hub.device_info

        # State
        self._is_on = False
        self._preset_mode = self._runtime_manager.get_last_preset()
        self._got_initial_state = False

    @property
    def is_on(self) -> bool:
        return self._is_on

    @property
    def preset_mode(self) -> str | None:
        return self._preset_mode

    @property
    def extra_state_attributes(self) -> dict:
        # Get connection status from hub
        hub_data = self._hub.get_coordinator_data()
        
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
            # Delayed turn-off attributes
            "delayed_off_active": self._delayed_off_active,
            "delayed_off_remaining": self._delayed_off_remaining,
            "delayed_off_delay": current_options.get("fan_auto_off_delay", 10),
        }
        
        # Add scheduled time if active
        if self._delayed_off_scheduled_time:
            attributes["delayed_off_scheduled_time"] = self._delayed_off_scheduled_time.isoformat()
        
        return attributes

    async def async_added_to_hass(self):
        """Called when entity is added to hass."""
        _LOGGER.info("ThermexFan entity added to hass: %s", self.entity_id)
        self._unsub = async_dispatcher_connect(self.hass, THERMEX_NOTIFY, self._handle_notify)
        _LOGGER.debug("ThermexFan: awaiting initial notify for state")
        # Use a longer timeout and check if startup is complete
        async_call_later(self.hass, 15, self._fallback_status)

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
        self.schedule_update_ha_state()

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        speed = _MODE_TO_VALUE[preset_mode]
        await self._hub.send_request("Update", {"Fan": {"fanonoff": int(speed > 0), "fanspeed": speed}})

    async def async_turn_on(self, percentage=None, preset_mode=None, **kwargs) -> None:
        if preset_mode:
            mode = preset_mode
        elif self._preset_mode and self._preset_mode != "off":
            mode = self._preset_mode
        else:
            mode = "medium"

        await self.async_set_preset_mode(mode)
        self._runtime_manager.start()
        self._runtime_manager.set_last_preset(mode)
        await self._runtime_manager.save()
        self._is_on = True
        self._preset_mode = mode
        self.schedule_update_ha_state()

    async def async_turn_off(self, **kwargs) -> None:
        await self.cancel_delayed_off()  # Cancel any delayed turn-off
        await self.async_set_preset_mode("off")
        self._runtime_manager.stop()
        self._runtime_manager.set_last_preset("off")
        await self._runtime_manager.save()
        self._is_on = False
        self._preset_mode = "off"
        self.schedule_update_ha_state()

    async def async_reset(self, **kwargs) -> None:
        self._runtime_manager.reset()
        await self._runtime_manager.save()
        self.schedule_update_ha_state()

    async def start_delayed_off(self) -> None:
        """Start the delayed turn-off timer."""
        _LOGGER.info("start_delayed_off service called")
        
        if not self._is_on:
            _LOGGER.warning("Cannot start delayed turn-off: fan is not running")
            return

        # Cancel any existing delayed turn-off
        await self.cancel_delayed_off()

        # For debugging, use 2 minutes instead of config value
        # Get current options from config entry
        current_options = self._entry.options
        # delay_minutes = max(1, min(120, current_options.get("fan_auto_off_delay", 10)))
        delay_minutes = 2  # DEBUG: Use 2 minutes for testing
        
        _LOGGER.info("DEBUG: Using %d minutes for delayed turn-off", delay_minutes)
        
        self._delayed_off_active = True
        self._delayed_off_remaining = delay_minutes
        
        # Calculate scheduled time
        from datetime import datetime, timedelta
        from homeassistant.util import dt as dt_util
        
        self._delayed_off_scheduled_time = dt_util.now() + timedelta(minutes=delay_minutes)

        _LOGGER.info("Starting delayed turn-off: %d minutes (until %s)", delay_minutes, self._delayed_off_scheduled_time.strftime("%H:%M"))
        _LOGGER.debug("Delayed turn-off details: active=%s, remaining=%d, handle=%s", self._delayed_off_active, self._delayed_off_remaining, self._delayed_off_handle is not None)
        
        # Schedule the turn-off
        self._delayed_off_handle = async_call_later(
            self.hass, delay_minutes * 60, self._handle_delayed_off
        )
        
        _LOGGER.debug("Delayed turn-off scheduled: handle=%s, seconds=%d", self._delayed_off_handle is not None, delay_minutes * 60)
        
        # Start countdown timer (update every minute)
        async_call_later(self.hass, 60, self._update_countdown)
        
        self.schedule_update_ha_state()
        
        # Notify other entities about delayed turn-off activation
        from .const import THERMEX_NOTIFY
        async_dispatcher_send(
            self.hass,
            THERMEX_NOTIFY,
            "delayed_turn_off",
            {
                "active": True, 
                "scheduled_time": self._delayed_off_scheduled_time.isoformat(),
                "remaining": delay_minutes
            },
        )
        
        # Notify other entities about delayed turn-off status change
        from .const import THERMEX_NOTIFY
        async_dispatcher_send(
            self.hass,
            THERMEX_NOTIFY,
            "delayed_turn_off",
            {"active": True, "scheduled_time": self._delayed_off_scheduled_time.isoformat()},
        )

    async def cancel_delayed_off(self) -> None:
        """Cancel the delayed turn-off timer."""
        if self._delayed_off_handle:
            self._delayed_off_handle()
            self._delayed_off_handle = None

        self._delayed_off_active = False
        self._delayed_off_remaining = 0
        self._delayed_off_scheduled_time = None
        self.schedule_update_ha_state()
        _LOGGER.info("Delayed turn-off cancelled")
        
        # Notify other entities about delayed turn-off status change
        from .const import THERMEX_NOTIFY
        async_dispatcher_send(
            self.hass,
            THERMEX_NOTIFY,
            "delayed_turn_off",
            {"active": False, "scheduled_time": None},
        )

    def _update_countdown(self, _now=None) -> None:
        """Update the countdown timer display."""
        if not self._delayed_off_active:
            return

        # Decrement the remaining time
        if self._delayed_off_remaining > 0:
            self._delayed_off_remaining -= 1
            self.schedule_update_ha_state()
            
            # Schedule next update in 1 minute if still active
            if self._delayed_off_remaining > 0:
                async_call_later(self.hass, 60, self._update_countdown)

    async def _handle_delayed_off(self, _now) -> None:
        """Handle the delayed turn-off event."""
        _LOGGER.info("Executing delayed turn-off - fan should turn off now")
        _LOGGER.debug("Current fan state before turn-off: is_on=%s, preset=%s", self._is_on, self._preset_mode)
        
        # Clear delayed turn-off state first
        self._delayed_off_handle = None
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
        from .const import THERMEX_NOTIFY
        async_dispatcher_send(
            self.hass,
            THERMEX_NOTIFY,
            "delayed_turn_off",
            {"active": False, "scheduled_time": None},
        )

    async def async_will_remove_from_hass(self):
        """Cancel any pending timers when entity is removed."""
        if self._unsub:
            self._unsub()
        await self.cancel_delayed_off()

    async def _handle_auto_off(self, _now):
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
