import logging
from homeassistant.components.switch import SwitchEntity
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass, config_entry, async_add_entities):
    data = hass.data[DOMAIN][config_entry.entry_id]
    status = data["status"]
    listeners = data["listeners"]

    entities = []

    if "Fan" in status:
        entities.append(ThermexFanSwitch(config_entry.entry_id, hass))

    async_add_entities(entities)

class ThermexFanSwitch(SwitchEntity):
    def __init__(self, entry_id, hass):
        self._entry_id = entry_id
        self.hass = hass
        self._attr_name = "Thermex Fan"
        self._unique_id = f"{entry_id}_fan"
        hass.data[DOMAIN][entry_id]["listeners"].append(self.async_update_callback)

    @property
    def is_on(self):
        return self._status().get("fanonoff", 0) == 1

    def _status(self):
        return self.hass.data[DOMAIN][self._entry_id]["status"].get("Fan", {})

    async def async_turn_on(self, **kwargs):
        api = self.hass.data[DOMAIN][self._entry_id]["api"]
        await api.send_request("Update", {"fan": {"fanonoff": 1}})

    async def async_turn_off(self, **kwargs):
        api = self.hass.data[DOMAIN][self._entry_id]["api"]
        await api.send_request("Update", {"fan": {"fanonoff": 0}})

    async def async_update_callback(self):
        self.async_write_ha_state()