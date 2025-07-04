# File: binary_sensor.py
"""
Thermex API binary sensor for filter‐life runtime alert.
"""
import logging

from homeassistant.components.binary_sensor import (
    BinarySensorEntity, 
    BinarySensorDeviceClass,
)
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.storage import Store
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.core import callback

from .const import DOMAIN, THERMEX_NOTIFY
from .hub import ThermexHub

_LOGGER = logging.getLogger(__name__)
STORAGE_VERSION = 1

async def async_setup_entry(hass, entry, async_add_entities):
    """Set up the Thermex filter‐alert binary sensor."""
    hub: ThermexHub = hass.data[DOMAIN][entry.entry_id]
    store = Store(
        hass, STORAGE_VERSION, f"{DOMAIN}_{entry.entry_id}_runtime.json"
    )
    data = await store.async_load() or {}

    device_info = DeviceInfo(
        identifiers={(DOMAIN, hub.unique_id)},
        manufacturer="Thermex",
        name=f"Thermex Hood ({hub._host})",
        model="ESP-API",
    )

    async_add_entities([
        ThermexFilterAlert(hub, store, data, entry.options, device_info)
    ], update_before_add=True)

class ThermexFilterAlert(BinarySensorEntity):
    """Binary sensor that goes ON when runtime exceeds threshold."""
    _attr_device_class = BinarySensorDeviceClass.PROBLEM
    _attr_name = "Thermex Fan Threshold Exceeded"

    def __init__(self, hub, store, data, options, device_info):
        self._hub = hub
        self._store = store
        self._data = data
        self._options = options
        self._attr_device_info = device_info
        self._attr_unique_id = f"{hub.unique_id}_threshold_alert"
        self._unsub = None

    @property
    def is_on(self) -> bool:
        return (
            self._data.get("runtime_hours", 0.0)
            >= self._options.get("runtime_threshold", 30)
        )

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
