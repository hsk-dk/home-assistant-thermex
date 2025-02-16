import logging
from homeassistant.helpers.entity import Entity
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
    _attr_color_mode = ColorMode.BRIGHTNESS
    _attr_supported_color_modes = {ColorMode.BRIGHTNESS}

    def __init__(self, coordinator, name="Thermex Light"):
        """Initialize the light entity."""
        self._coordinator = coordinator
        self._attr_name = name
        self._state = None
        self._attr_brightness = None
        self._attr_unique_id = "fsfdsfsdfsdf3r" 

    @property
    def unique_id(self):
        """Return the name of the light."""
        return self._attr_unique_id

    @property
    def name(self):
        """Return the name of the light."""
        return self._attr_name

    @property
    def supported_color_modes(self):
        """Set of supported color modes."""
        return self._attr_supported_color_modes

    @property
    def color_mode(self):
        """Current color mode of the light."""
        if self._attr_state == True:
            if self._attr_brightness is not None:
                self._attr_color_mode = ColorMode.BRIGHTNESS
            self._attr_color_mode = ColorMode.ONOFF
        self._attr_color_mode = ColorMode.UNKNOWN
        return self._attr_color_mode

    @property
    def is_on(self):
        """Return true if the light is on."""
        return self._attr_state
    
    @property
    def brightness(self):
        """Return the brightness of the light."""
        return self._attr_brightness

    @property
    def icon(self) -> str | None:
        """Icon based on state."""
        if self._attr_state:
            return "mdi:pot-steam"
        else:
            return "mdi:pot-steam-outline"

    async def async_update(self):
        """Fetch the latest data from the coordinator."""
        data = await self._coordinator.async_get_data()
        light_data = data.get("Light", {})
        _LOGGER.debug("Light status modtaget: %s", light_data)

        lightonoff = light_data.get("lightonoff")
        _LOGGER.debug("Light on/off status: %s", lightonoff)

        if lightonoff == 1:
            self._attr_state = True
        elif lightonoff == 0:
            self._attr_state = False
        else:
            _LOGGER.warning("Unexpected value for lightonoff: %s", lightonoff)
            self._attr_state = None

        _LOGGER.debug("Light status sat: %s", self._state)
        self._brightness = light_data.get("lightbrightness")
        if self._attr_state == True:
            if self._attr_brightness is not None:
                self._attr_color_mode = ColorMode.BRIGHTNESS
            self._attr_color_mode = ColorMode.ONOFF
        self._attr_color_mode = ColorMode.UNKNOWN

    async def async_turn_on(self, **kwargs):
        """Turn on the light."""
        brightness = kwargs.get("brightness")
        await self._coordinator.update_light(lightonoff=1, brightness=brightness)

    async def async_turn_off(self, **kwargs):
        """Turn off the light."""
        await self._coordinator.update_light(lightonoff=0)
