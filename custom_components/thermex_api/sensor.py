# File: custom_components/thermex_api/sensor.py
"""
Thermex API sensors for runtime tracking of the Thermex Fan.
Creates persistent sensors for:
 - runtime_hours
 - last_reset
 - filter_time
"""
import logging
from datetime import datetime

from homeassistant.components.sensor import SensorEntity, SensorDeviceClass
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.storage import Store
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.core import callback
from homeassistant.util.dt import parse_datetime

from .const import DOMAIN, THERMEX_NOTIFY
from .hub import ThermexHub
from .runtime_manager import RuntimeManager  # Ensure this is implemented as discussed

_LOGGER = logging.getLogger(__name__)

STORAGE_VERSION = 1

async def async_setup_entry(hass, entry, async_add_entities):
    """Set up persistent runtime-tracking sensors for the Thermex fan."""
    entry_data = hass.data[DOMAIN][entry.entry_id]
    hub = entry_data["hub"]
    runtime_manager = entry_data["runtime_manager"]

    device_info = hub.device_info

    async_add_entities([
        RuntimeHoursSensor(hub, runtime_manager, device_info),
        LastResetSensor(hub, runtime_manager, device_info),
        FilterTimeSensor(hub, runtime_manager, device_info),
        ConnectionStatusSensor(hub, runtime_manager, device_info),
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
    _attr_unit_of_measurement = "h"
    _attr_state_class = "measurement"

    def __init__(self, hub, runtime_manager, device_info):
        super().__init__(hub, runtime_manager, device_info)
        self._attr_unique_id = f"{hub.unique_id}_runtime_hours"
        self._attr_translation_key = "thermex_sensor_runtime_hours"
 
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


class FilterTimeSensor(BaseRuntimeSensor):
    """Sensor to display current filter time from the runtime manager."""

    _attr_icon = "mdi:clock"
    _attr_native_unit_of_measurement = "h"
    _attr_state_class = "measurement"

    def __init__(self, hub, runtime_manager, device_info):
        super().__init__(hub, runtime_manager, device_info)
        self._attr_unique_id = f"{hub.unique_id}_filter_time"
        self._attr_translation_key = "thermex_sensor_filter_time"
     
    @property
    def native_value(self):
        # If filter time is equivalent to runtime_hours, simply return that
        return self._runtime_manager.get_filter_time()
        # If you want to display runtime_hours as filter time, use:
        # return self._runtime_manager.get_runtime_hours()


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
    def extra_state_attributes(self) -> dict:
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
