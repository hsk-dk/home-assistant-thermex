import logging
from homeassistant.helpers.entity import Entity

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)
async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    """Set up the Thermex fan sensor platform."""
    _LOGGER.debug("Sensor.py Setting up Thermex fan sensor platform")
    
    # Hent API fra hass.data
    api = hass.data[DOMAIN]
    
    # Opret og tilføj fan sensor til Home Assistant
    async_add_entities([ThermexFanSensor(api)], True)
    
class ThermexFanSensor(Entity):
    """Representation of a fan sensor."""

    def __init__(self, coordinator):
        """Initialize the sensor."""
        self._state = None
        self._coordinator = coordinator
        self._speeds = {
            0: "off",
            1: "lav",
            2: "mellem",
            3: "høj",
            4: "boost"
        }
        self._attr_unique_id = "fdddsfdsfsdfsdf3r" 

        _LOGGER.debug("Sensor.py Thermex ThermexFanSensor initialiseret")

    @property
    def unique_id(self):
        """Return the name of the light."""
        return self._attr_unique_id

    @property
    def name(self):
        """Return the name of the sensor."""
        return "Thermex Fan Sensor"

    @property
    def state(self):
        """Return the state of the sensor."""
        return self._state

    @property
    def unit_of_measurement(self):
        """Return the unit of measurement."""
        return None

    @property
    def icon(self) -> str | None:
        """Icon based on state."""
        if self._attr_state == "Lav":
            return "mdi:fan-speed-1"
        elif self._attr_state == "Mellem":
            return "mdi:fan-speed-2"
        elif self._attr_state == "Høj":
            return "mdi:fan-speed-3"
        elif self._attr_state == "Boost":
            return "mdi:fan-plus"
        else:
            return "mdi:fan-off"

    async def async_update(self):
        """Fetch the latest data from the coordinator."""
        data = await self._coordinator.async_get_data()
        fan_data = data.get("Fan", {})
        self._state = self._speeds.get(fan_data.get("fanspeed", 0), "ukendt")
    
