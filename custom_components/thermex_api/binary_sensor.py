# File: binary_sensor.py
"""
Thermex API binary sensor for filter‐life runtime alert.
"""
import logging
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorEntity, 
    BinarySensorDeviceClass,
)
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.core import callback

from .runtime_manager import RuntimeManager
from .const import DOMAIN, THERMEX_NOTIFY
from .hub import ThermexHub

_LOGGER = logging.getLogger(__name__)
STORAGE_VERSION = 1

async def async_setup_entry(hass, entry, async_add_entities):
    """Set up the Thermex filter‐alert binary sensor."""
    entry_data = hass.data[DOMAIN][entry.entry_id]
    hub: ThermexHub = entry_data["hub"]
    runtime_manager: RuntimeManager = entry_data["runtime_manager"]

    device_info = hub.device_info

    async_add_entities([
        ThermexFilterAlert(hub, runtime_manager, entry.options, device_info)
    ], update_before_add=True)

class ThermexFilterAlert(BinarySensorEntity):
    """Binary sensor that goes ON when runtime exceeds threshold."""
    _attr_device_class = BinarySensorDeviceClass.PROBLEM

    def __init__(self, hub, runtime_manager, options, device_info):
        self._hub = hub
        self._runtime_manager = runtime_manager
        self._options = options
        self._attr_device_info = device_info
        self._attr_unique_id = f"{hub.unique_id}_threshold_alert"
        self._attr_translation_key = "thermex_binary_sensor_threshold_alert"
        self._attr_has_entity_name = True
        self._unsub = None

    @property
    def is_on(self) -> bool:
        """Return True if filter alert should be triggered."""
        # Check runtime hours threshold
        runtime_hours = self._runtime_manager.get_runtime_hours()
        hours_threshold = self._options.get("fan_alert_hours", 30)
        hours_exceeded = runtime_hours >= hours_threshold
        
        # Check days since reset threshold
        days_since_reset = self._runtime_manager.get_days_since_reset()
        days_threshold = self._options.get("fan_alert_days", 90)
        days_exceeded = False
        
        if days_since_reset is not None:
            # Normal case: we have a reset date
            days_exceeded = days_since_reset >= days_threshold
        else:
            # No reset date recorded - assume filter needs attention after some runtime
            # Only trigger days-based alert if we have significant runtime hours (> 5 hours)
            # This prevents false alerts on new installations with no usage
            days_exceeded = runtime_hours > 5
        
        # Trigger alert if either condition is met
        return hours_exceeded or days_exceeded
    
    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional state attributes including dual threshold information."""
        runtime_hours = self._runtime_manager.get_runtime_hours()
        days_since_reset = self._runtime_manager.get_days_since_reset()
        hours_threshold = self._options.get("fan_alert_hours", 30)
        days_threshold = self._options.get("fan_alert_days", 90)
        
        hours_exceeded = runtime_hours >= hours_threshold
        days_exceeded = False
        
        if days_since_reset is not None:
            # Normal case: we have a reset date
            days_exceeded = days_since_reset >= days_threshold
        else:
            # No reset date recorded - trigger if significant runtime
            days_exceeded = runtime_hours > 5
        
        # Get hub data for connection status
        hub_data = self._hub.get_coordinator_data()
        
        return {
            "runtime_hours": runtime_hours,
            "days_since_reset": days_since_reset if days_since_reset is not None else "No reset date",
            "hours_threshold": hours_threshold,
            "days_threshold": days_threshold,
            "hours_exceeded": hours_exceeded,
            "days_exceeded": days_exceeded,
            "last_reset": self._runtime_manager.get_last_reset() or "never",
            "trigger_reason": self._get_trigger_reason(hours_exceeded, days_exceeded, days_since_reset),
            # Connection status attributes
            "connection_state": hub_data.get("connection_state", "unknown"),
            "watchdog_active": hub_data.get("watchdog_active", False),
            "time_since_activity": hub_data.get("time_since_activity", 0),
        }
    
    def _get_trigger_reason(self, hours_exceeded: bool, days_exceeded: bool, days_since_reset) -> str:
        """Get a human-readable reason for why the alert is triggered."""
        if not (hours_exceeded or days_exceeded):
            return "No alert"
        
        reasons = []
        if hours_exceeded:
            reasons.append("Runtime hours exceeded")
        if days_exceeded:
            if days_since_reset is not None:
                reasons.append("Days since reset exceeded")
            else:
                reasons.append("No filter reset date recorded")
        
        return " and ".join(reasons)

    async def async_added_to_hass(self):
        self._unsub = async_dispatcher_connect(
            self.hass, THERMEX_NOTIFY, self._handle_notify
        )
        # push initial state
        self.async_write_ha_state()

    async def async_will_remove_from_hass(self):
        if self._unsub:
            self._unsub()

    @callback
    def _handle_notify(self, ntf_type, data):
        if ntf_type.lower() == "fan":
            # state may have changed
            self.async_write_ha_state()
