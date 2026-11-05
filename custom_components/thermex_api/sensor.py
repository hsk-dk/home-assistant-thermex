# File: custom_components/thermex_api/sensor.py
"""
Thermex API sensors for runtime tracking of the Thermex Fan.
Creates persistent sensors for:
 - last_reset
 - filter_time
"""
import logging
from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.core import callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.event import async_call_later
from homeassistant.util import dt as dt_util
from homeassistant.util.dt import parse_datetime

from .const import RUNTIME_UPDATE_INTERVAL, THERMEX_NOTIFY
from .data import ThermexConfigEntry
from .entity_lookup import find_fan_entity_id

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass, entry: ThermexConfigEntry, async_add_entities):
    """Set up persistent runtime-tracking sensors for the Thermex fan."""
    hub = entry.runtime_data.hub
    runtime_manager = entry.runtime_data.runtime_manager

    device_info = hub.device_info

    async_add_entities([
        LastResetSensor(hub, runtime_manager, device_info),
        RuntimeHoursSensor(hub, runtime_manager, device_info),
        ConnectionStatusSensor(hub, runtime_manager, device_info),
        DelayedTurnOffSensor(hub, runtime_manager, device_info, entry.entry_id),
    ], update_before_add=True)


class BaseRuntimeSensor(SensorEntity):
    """Base class for runtime sensors that listen to THERMEX_NOTIFY."""
    def __init__(self, hub, runtime_manager, device_info):
        self._hub = hub
        self._runtime_manager = runtime_manager
        self._attr_device_info = device_info
        self._attr_has_entity_name = True
        self._unsub = None

    async def async_added_to_hass(self):
        self._unsub = async_dispatcher_connect(
            self.hass, THERMEX_NOTIFY, self._handle_notify
        )
        self.async_write_ha_state()

    async def async_will_remove_from_hass(self):
        if self._unsub:
            self._unsub()

    @callback
    def _handle_notify(self, ntf_type, data):
        """On any fan notify, refresh this sensor."""
        if ntf_type.lower() == "fan":
            self.async_write_ha_state()


class RuntimeHoursSensor(BaseRuntimeSensor):
    """Sensor for the cumulative runtime hours of the Thermex fan."""
    _attr_unit_of_measurement = "h"  # type: ignore[assignment]
    _attr_state_class = "measurement"

    def __init__(self, hub, runtime_manager, device_info):
        super().__init__(hub, runtime_manager, device_info)
        self._attr_unique_id = f"{hub.unique_id}_runtime_hours"
        self._attr_translation_key = "thermex_sensor_runtime_hours"
        self._update_timer = None
        self._fan_is_running = False
        
    async def async_added_to_hass(self):
        """Set up the sensor and start periodic updates."""
        await super().async_added_to_hass()
        # Updates will be scheduled when fan starts running
        
    async def async_will_remove_from_hass(self):
        """Clean up when removing sensor."""
        await super().async_will_remove_from_hass()
        if self._update_timer:
            self._update_timer()
            self._update_timer = None
    
    @callback
    def _handle_notify(self, ntf_type, data):
        """Handle fan state changes and update scheduling."""
        if ntf_type.lower() != "fan":
            return
        
        # Check if fan is running
        fan_data = data.get("Fan", {})
        fan_speed = fan_data.get("fanspeed", 0)
        fan_on = bool(fan_data.get("fanonoff", 0)) and fan_speed != 0
        
        # Update state
        self.async_write_ha_state()
        
        # Manage periodic updates based on fan state
        if fan_on and not self._fan_is_running:
            # Fan just turned on - start periodic updates
            self._fan_is_running = True
            self._schedule_update()
        elif not fan_on and self._fan_is_running:
            # Fan just turned off - stop periodic updates
            self._fan_is_running = False
            if self._update_timer:
                self._update_timer()
                self._update_timer = None
            
    def _schedule_update(self):
        """Schedule the next update (only when fan is running)."""
        if self._update_timer:
            self._update_timer()
        
        # Only schedule if fan is still running
        if self._fan_is_running:
            self._update_timer = async_call_later(
                self.hass, RUNTIME_UPDATE_INTERVAL, self._periodic_update
            )
    
    async def _periodic_update(self, _):
        """Periodic update callback to track runtime accumulation."""
        self.async_write_ha_state()
        # Schedule the next update (will check if fan is still running)
        self._schedule_update()
 
    @property
    def native_value(self):
        return self._runtime_manager.get_runtime_hours()


class LastResetSensor(BaseRuntimeSensor):
    """Timestamp when the runtime counter was last reset."""

    _attr_device_class = SensorDeviceClass.TIMESTAMP

    def __init__(self, hub, runtime_manager, device_info):
        super().__init__(hub, runtime_manager, device_info)
        self._attr_unique_id = f"{hub.unique_id}_last_reset"
        self._attr_translation_key = "thermex_sensor_last_reset"

    @property
    def native_value(self):
        iso = self._runtime_manager.get_last_reset()
        if iso:
            return parse_datetime(iso)
        return None


class ConnectionStatusSensor(BaseRuntimeSensor):
    """Sensor to display connection status and diagnostic information."""

    _attr_icon = "mdi:connection"

    def __init__(self, hub, runtime_manager, device_info):
        super().__init__(hub, runtime_manager, device_info)
        self._attr_unique_id = f"{hub.unique_id}_connection_status"
        self._attr_translation_key = "thermex_sensor_connection_status"
     
    @property
    def native_value(self):
        """Return the connection state with protocol version as the sensor value."""
        hub_data = self._hub.get_coordinator_data()
        connection_state = hub_data.get("connection_state", "unknown")
        protocol_version = self._hub.protocol_version
        
        if connection_state == "connected" and protocol_version:
            return f"connected (v{protocol_version})"
        else:
            return connection_state
    
    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return connection diagnostic information as attributes."""
        hub_data = self._hub.get_coordinator_data()
        
        return {
            "last_error": hub_data.get("last_error"),
            "watchdog_active": hub_data.get("watchdog_active", False),
            "time_since_activity": hub_data.get("time_since_activity", 0),
            "heartbeat_interval": hub_data.get("heartbeat_interval", 30),
            "connection_timeout": hub_data.get("connection_timeout", 120),
            "protocol_version": self._hub.protocol_version,
        }
    
    @callback
    def _handle_notify(self, ntf_type, data):
        """Update on any notification to refresh connection status."""
        # Update connection status on any activity
        self.async_write_ha_state()


class DelayedTurnOffSensor(BaseRuntimeSensor):
    """Sensor that shows the scheduled turn-off time for the fan."""
    
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    
    def __init__(self, hub, runtime_manager, device_info, entry_id):
        super().__init__(hub, runtime_manager, device_info)
        self._entry_id = entry_id
        self._attr_unique_id = f"{hub.unique_id}_delayed_turn_off_time"
        self._attr_translation_key = "thermex_sensor_delayed_turn_off"
        
    async def async_added_to_hass(self):
        """Listen for delayed turn-off notifications."""
        await super().async_added_to_hass()
        # Listen specifically for delayed turn-off notifications
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass, THERMEX_NOTIFY, self._handle_delayed_off_notify
            )
        )
        
    @callback
    def _handle_delayed_off_notify(self, ntf_type, data):
        """Handle delayed turn-off notification."""
        if ntf_type == "delayed_turn_off":
            _LOGGER.debug("DelayedTurnOffSensor received notification: %s", data)
            # Force update immediately when we get a delayed turn-off notification
            self.async_write_ha_state()
        elif ntf_type == "fan":
            # Also update when fan state changes, as this might affect our display
            _LOGGER.debug("DelayedTurnOffSensor received fan notification, updating state")
            self.async_write_ha_state()
        
    def _fan_state(self):
        """Return the fan's state object, found via the entity registry."""
        fan_entity_id = find_fan_entity_id(self.hass, self._hub.unique_id)
        return self.hass.states.get(fan_entity_id) if fan_entity_id else None

    @property
    def native_value(self):
        """Return the scheduled turn-off time."""
        fan_state = self._fan_state()
        if not fan_state:
            return None
        scheduled_time = fan_state.attributes.get("delayed_off_scheduled_time")
        if not scheduled_time:
            return None
        parsed_dt = parse_datetime(scheduled_time)
        if parsed_dt and parsed_dt.tzinfo is None:
            parsed_dt = parsed_dt.replace(tzinfo=dt_util.DEFAULT_TIME_ZONE)
        return parsed_dt

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional delayed turn-off information."""
        fan_state = self._fan_state()
        attrs = fan_state.attributes if fan_state else {}
        return {
            "delayed_off_active": attrs.get("delayed_off_active", False),
            "delayed_off_remaining": attrs.get("delayed_off_remaining", 0),
            "delayed_off_delay": attrs.get("delayed_off_delay", 10),
        }
