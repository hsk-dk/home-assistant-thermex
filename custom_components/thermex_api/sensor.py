# File: sensor.py
"""
Thermex API sensors for runtime tracking of the Thermex Fan.
Creates persistent sensors for:
 - runtime_hours
 - last_reset
"""
import logging
from datetime import datetime

from homeassistant.components.sensor import SensorEntity, SensorDeviceClass
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.storage import Store
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.core import callback
from homeassistant.util.dt import utc_from_timestamp, parse_datetime

from .const import DOMAIN, THERMEX_NOTIFY
from .hub import ThermexHub

_LOGGER = logging.getLogger(__name__)

STORAGE_VERSION = 1

async def async_setup_entry(hass, entry, async_add_entities):
    """Set up persistent runtime-tracking sensors for the Thermex fan."""
    hub: ThermexHub = hass.data[DOMAIN][entry.entry_id]
    store = Store(
        hass,
        STORAGE_VERSION,
        f"{DOMAIN}_{entry.entry_id}_runtime.json"
    )
    data = await store.async_load() or {}

    device_info = DeviceInfo(
        identifiers={(DOMAIN, hub.unique_id)},
        manufacturer="Thermex",
        name=f"Thermex Hood ({hub._host})",
        model="ESP-API",
    )

    async_add_entities([
        RuntimeHoursSensor(hub, store, data, entry.options, device_info),
        #LastStartSensor(hub, store, data, entry.options, device_info),
        LastResetSensor(hub, store, data, entry.options, device_info),
        FilterTimeSensor(coordinator, hub),
    ], update_before_add=True)


class BaseRuntimeSensor(SensorEntity):
    """Base class for runtime sensors that listen to THERMEX_NOTIFY."""
    def __init__(self, hub, store, data, options, device_info):
        self._hub = hub
        self._store = store
        self._data = data
        self._options = options
        self._attr_device_info = device_info
        self._unsub = None

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
        """On any fan notify, refresh this sensor."""
        if ntf_type.lower() == "fan":
            self.async_write_ha_state()


class RuntimeHoursSensor(BaseRuntimeSensor):
    """Sensor for the cumulative runtime hours of the Thermex fan."""
    _attr_name = "Thermex Fan Runtime"
    _attr_unit_of_measurement = "h"
    _attr_state_class = "measurement"

    def __init__(self, hub, store, data, options, device_info):
        super().__init__(hub, store, data, options, device_info)
        self._attr_unique_id = f"{hub.unique_id}_runtime_hours"

    @property
    def native_value(self):
        return round(self._data.get("runtime_hours", 0.0), 2)


#class LastStartSensor(BaseRuntimeSensor):
#    """Timestamp when the Thermex fan was last turned ON."""
#    _attr_name = "Thermex Fan Last Start"
#    _attr_device_class = SensorDeviceClass.TIMESTAMP
#
#    def __init__(self, hub, store, data, options, device_info):
#        super().__init__(hub, store, data, options, device_info)
#        self._attr_unique_id = f"{hub.unique_id}_last_start"
#
#    @property
#    def native_value(self):
#        """Return `datetime` of last ON timestamp, or None."""
#        ts = self._data.get("last_start")
#        if ts is not None:
#            # convert stored Unix timestamp -> aware UTC datetime
#            return utc_from_timestamp(ts)
#        return None


class LastResetSensor(BaseRuntimeSensor):
    """Timestamp when the runtime counter was last reset."""
    _attr_name = "Thermex Fan Last Reset"
    _attr_device_class = SensorDeviceClass.TIMESTAMP

    def __init__(self, hub, store, data, options, device_info):
        super().__init__(hub, store, data, options, device_info)
        self._attr_unique_id = f"{hub.unique_id}_last_reset"

    @property
    def native_value(self):
        """Return `datetime` of last reset, or None."""
        iso = self._data.get("last_reset")
        if iso:
            # parse stored ISO string -> aware datetime
            return parse_datetime(iso)
        return None
     
  class FilterTimeSensor(CoordinatorEntity, SensorEntity):
     """Sensor to display current filter time from the Thermex hub."""

     _attr_name = "Thermex Filter Time"
     _attr_icon = "mdi:clock"
     _attr_native_unit_of_measurement = "h"
     _attr_state_class = "measurement"

   def __init__(self, coordinator, hub):
      super().__init__(coordinator)
      self._hub = hub
      self._attr_unique_id = f"{hub.unique_id}_filter_time"

    @property
    def native_value(self):
        return self.coordinator.data.get("filtertime", 0)
