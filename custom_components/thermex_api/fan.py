"""Thermex Fan entity with discrete presets and persistent runtime tracking."""
import logging
from datetime import datetime

from homeassistant.components.fan import FanEntity, FanEntityFeature
from homeassistant.core import callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
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
    async_add_entities([ThermexFan(hub, runtime_manager, entry.options)], update_before_add=True)

    platform = entity_platform.async_get_current_platform()
    platform.async_register_entity_service(
        "reset_runtime",
        {},
        "async_reset"
    )


class ThermexFan(FanEntity):
    """Thermex extractor fan with presets and runtime tracking."""

    _attr_supported_features = (
        FanEntityFeature.PRESET_MODE
        | FanEntityFeature.TURN_ON
        | FanEntityFeature.TURN_OFF
    )
    _attr_preset_modes = PRESET_MODES

    def __init__(self, hub: ThermexHub, runtime_manager: RuntimeManager, options: dict):
        self._hub = hub
        self._runtime_manager = runtime_manager
        self._options = options
        self._auto_off_handle = None
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
        
        return {
            "runtime_hours": self._runtime_manager.get_runtime_hours(),
            "filter_time": self._runtime_manager.get_filter_time(),
            "last_reset": self._runtime_manager.get_last_reset() or "never",
            "last_preset": self._runtime_manager.get_last_preset(),
            "threshold": self._options.get("runtime_threshold", 30),
            "alert": self._runtime_manager.get_runtime_hours() >= self._options.get("runtime_threshold", 30),
            "is_on": self._is_on,
            # Connection status attributes
            "connection_state": hub_data.get("connection_state", "unknown"),
            "last_error": hub_data.get("last_error"),
            "watchdog_active": hub_data.get("watchdog_active", False),
            "time_since_activity": hub_data.get("time_since_activity", 0),
            "heartbeat_interval": hub_data.get("heartbeat_interval", 30),
            "connection_timeout": hub_data.get("connection_timeout", 120),
        }

    async def async_added_to_hass(self):
        self._unsub = async_dispatcher_connect(self.hass, THERMEX_NOTIFY, self._handle_notify)
        _LOGGER.debug("ThermexFan: awaiting initial notify for state")
        # Use a longer timeout and check if startup is complete
        async_call_later(self.hass, 15, self._fallback_status)

    async def async_will_remove_from_hass(self):
        if self._unsub:
            self._unsub()

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
