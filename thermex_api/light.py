import logging
#from homeassistant.helpers.entity import Entity
from homeassistant.components.light import ColorMode, LightEntity, LightEntityFeature

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    """Set up the Thermex fan sensor platform."""
    _LOGGER.debug("light.py Setting up Thermex Light platform")
    
    # Hent API fra hass.data
    api = hass.data[DOMAIN]
    
    # Opret og tilføj fan sensor til Home Assistant
    async_add_entities([ThermexLight(api)], True)

class ThermexLight(LightEntity):
    """Representation of a light entity."""

    def __init__(self, coordinator, name="Thermex Light"):
        """Initialize the light entity."""
        self._coordinator = coordinator
        self._name = name
        self._state = None
        self._brightness = None

    async def async_update(self):
        """Fetch the latest data from the coordinator."""
        data = await self._coordinator.async_get_data()
        light_data = data.get("Light", {})
        _LOGGER.debug("Light status modtaget: %s", light_data)

        lightonoff = light_data.get("lightonoff")
        _LOGGER.debug("Light on/off status: %s", lightonoff)

        if lightonoff == 1:
            self._state = True
        elif lightonoff == 0:
            self._state = False
        else:
            _LOGGER.warning("Unexpected value for lightonoff: %s", lightonoff)
            self._state = None

        _LOGGER.debug("Light status sat: %s", self._state)
        self._brightness = light_data.get("lightbrightness")

    @property
    def supported_color_modes(self):
        """Set of supported color modes."""
        return {ColorMode.ONOFF, ColorMode.BRIGHTNESS}

    @property
    def color_mode(self):
        """Current color mode of the light."""
        if self._brightness is not None:
            return ColorMode.BRIGHTNESS
        return ColorMode.ONOFF

    @property
    def name(self):
        """Return the name of the light."""
        return self._name

    @property
    def is_on(self):
        """Return true if the light is on."""
        return self._state

    async def async_turn_on(self, **kwargs):
        """Turn on the light."""
        brightness = kwargs.get("brightness")
        await self._coordinator.update_light(lightonoff=1, brightness=brightness)

    async def async_turn_off(self, **kwargs):
        """Turn off the light."""
        await self._coordinator.update_light(lightonoff=0)

    @property
    def brightness(self):
        """Return the brightness of the light."""
        return self._brightness
