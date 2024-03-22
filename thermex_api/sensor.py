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
        #self._api = api
        self._state = None
        self._coordinator = coordinator
        self._speeds = {
            0: "off",
            1: "lav",
            2: "mellem",
            3: "høj",
            4: "boost"
        }
        _LOGGER.debug("Sensor.py Thermex ThermexFanSensor initialiseret")

    async def async_update(self):
        """Fetch the latest data from the coordinator."""
        data = await self._coordinator.async_get_data()
        fan_data = data.get("Fan", {})
        self._state = self._speeds.get(fan_data.get("fanspeed", 0), "ukendt")
    
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
