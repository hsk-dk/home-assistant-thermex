# File: custom_components/thermex_api/sensor.py
"""
Thermex API sensors for runtime tracking of the Thermex Fan.
Creates persistent sensors for:
 - runtime_hours
 - last_reset
 - filter_time
"""
import logging
import asyncio
from datetime import datetime

from homeassistant.components.sensor import SensorEntity, SensorDeviceClass
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.storage import Store
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.core import callback
from homeassistant.util.dt import parse_datetime
from homeassistant.helpers.event import async_call_later

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


class PeriodicRuntimeSensor(BaseRuntimeSensor):
    """Enhanced runtime sensor that updates every minute when fan is running."""
    
    def __init__(self, hub, runtime_manager, device_info):
        super().__init__(hub, runtime_manager, device_info)
        self._update_timer = None
        self._update_interval = 60  # Update every 60 seconds
        self._fan_is_running = False
    
    async def async_added_to_hass(self):
        await super().async_added_to_hass()
        # Start the periodic update timer
        self._schedule_update()
    
    async def async_will_remove_from_hass(self):
        await super().async_will_remove_from_hass()
        # Cancel the periodic update timer
        if self._update_timer:
            self._update_timer()
            self._update_timer = None
    
    def _schedule_update(self):
        """Schedule the next update."""
        if self._update_timer:
            self._update_timer()
        
        self._update_timer = async_call_later(
            self.hass, 
            self._update_interval, 
            self._periodic_update
        )
    
    @callback
    def _periodic_update(self, _):
        """Periodic update callback - updates when fan is running."""
        if self._fan_is_running:
            # Fan is running, update the sensor
            self.async_write_ha_state()
        
        # Schedule next update
        self._schedule_update()
    
    @callback
    def _handle_notify(self, ntf_type, data):
        """Handle notifications and track fan state."""
        if ntf_type.lower() == "fan":
            # Update sensor state
            self.async_write_ha_state()
            
            # Track if fan is running based on the notification data
            if isinstance(data, dict) and "fan" in data:
                fan_data = data["fan"]
                # Check if fan mode indicates it's running (not "off")
                if isinstance(fan_data, dict):
                    mode = fan_data.get("mode", "off")
                    self._fan_is_running = mode != "off" and mode != 0
                elif isinstance(fan_data, str):
                    self._fan_is_running = fan_data != "off"
                else:
                    # Fallback: assume running if we got a fan notification
                    self._fan_is_running = True
            
            # Reset the timer to ensure regular updates start/stop appropriately
            self._schedule_update()


class RuntimeHoursSensor(PeriodicRuntimeSensor):
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


class FilterTimeSensor(PeriodicRuntimeSensor):
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
