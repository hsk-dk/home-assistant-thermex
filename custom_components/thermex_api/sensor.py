import logging
from homeassistant.components.sensor import SensorEntity
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass, config_entry, async_add_entities):
    data = hass.data[DOMAIN][config_entry.entry_id]
    status = data["status"]
    listeners = data["listeners"]

    entities = []

    if "Fan" in status and "fanspeed" in status["Fan"]:
        entities.append(ThermexFanSpeedSensor(config_entry.entry_id, hass))

    async_add_entities(entities)

class ThermexFanSpeedSensor(SensorEntity):
    def __init__(self, entry_id, hass):
        self._entry_id = entry_id
        self.hass = hass
        self._attr_name = "Thermex Fan Speed"
        self._unique_id = f"{entry_id}_fanspeed"
        self._attr_native_unit_of_measurement = "level"
        hass.data[DOMAIN][entry_id]["listeners"].append(self.async_update_callback)

    @property
    def native_value(self):
        return self._status().get("fanspeed")

    def _status(self):
        return self.hass.data[DOMAIN][self._entry_id]["status"].get("Fan", {})

    async def async_update_callback(self):
        self.async_write_ha_state()