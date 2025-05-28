import logging
from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    LightEntity,
    SUPPORT_BRIGHTNESS,
)
from homeassistant.const import STATE_ON

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass, config_entry, async_add_entities):
    data = hass.data[DOMAIN][config_entry.entry_id]
    status = data["status"]
    listeners = data["listeners"]

    entities = []

    if "Light" in status:
        entities.append(ThermexMainLight(config_entry.entry_id, hass))

    if "Decolight" in status:
        entities.append(ThermexDecoLight(config_entry.entry_id, hass))

    async_add_entities(entities)

class ThermexMainLight(LightEntity):
    def __init__(self, entry_id, hass):
        self._entry_id = entry_id
        self.hass = hass
        self._attr_supported_features = SUPPORT_BRIGHTNESS
        self._attr_name = "Thermex Light"
        self._unique_id = f"{entry_id}_mainlight"

        # Register update callback
        hass.data[DOMAIN][entry_id]["listeners"].append(self.async_update_callback)

    @property
    def is_on(self):
        return self._status().get("lightonoff", 0) == 1

    @property
    def brightness(self):
        raw = self._status().get("lightbrightness", 100)
        return int(raw / 100 * 255)

    def _status(self):
        return self.hass.data[DOMAIN][self._entry_id]["status"].get("Light", {})

    async def async_turn_on(self, **kwargs):
        api = self.hass.data[DOMAIN][self._entry_id]["api"]
        brightness = kwargs.get(ATTR_BRIGHTNESS, 255)
        payload = {
            "light": {
                "lightonoff": 1,
                "lightbrightness": int(brightness / 255 * 100)
            }
        }
        await api.send_request("Update", payload)

    async def async_turn_off(self, **kwargs):
        api = self.hass.data[DOMAIN][self._entry_id]["api"]
        await api.send_request("Update", {"light": {"lightonoff": 0}})

    async def async_update_callback(self):
        self.async_write_ha_state()

class ThermexDecoLight(LightEntity):
    def __init__(self, entry_id, hass):
        self._entry_id = entry_id
        self.hass = hass
        self._attr_supported_features = SUPPORT_BRIGHTNESS
        self._attr_name = "Thermex Deco Light"
        self._unique_id = f"{entry_id}_decolight"

        hass.data[DOMAIN][entry_id]["listeners"].append(self.async_update_callback)

    @property
    def is_on(self):
        return self._status().get("decolightonoff", 0) == 1

    @property
    def brightness(self):
        raw = self._status().get("decolightbrightness", 100)
        return int(raw / 100 * 255)

    def _status(self):
        return self.hass.data[DOMAIN][self._entry_id]["status"].get("Decolight", {})

    async def async_turn_on(self, **kwargs):
        api = self.hass.data[DOMAIN][self._entry_id]["api"]
        brightness = kwargs.get(ATTR_BRIGHTNESS, 255)
        payload = {
            "decolight": {
                "decolightonoff": 1,
                "decolightbrightness": int(brightness / 255 * 100)
            }
        }
        await api.send_request("Update", payload)

    async def async_turn_off(self, **kwargs):
        api = self.hass.data[DOMAIN][self._entry_id]["api"]
        await api.send_request("Update", {"decolight": {"decolightonoff": 0}})

    async def async_update_callback(self):
        self.async_write_ha_state()