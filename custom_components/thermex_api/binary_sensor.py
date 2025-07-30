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
from homeassistant.helpers.entity import DeviceInfo
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
        return (
            self._runtime_manager.get_runtime_hours()
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
