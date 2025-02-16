"""Platform for a generic switch."""
import logging

from homeassistant.components.switch import SwitchEntity

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    """Set up the Generic Switch platform."""
    # Hent API fra hass.data
    api = hass.data[DOMAIN]
    # Replace 'your_device_id' and 'Your Switch' with appropriate values
    async_add_entities([ThermexFanSwitch(api)], True)


class ThermexFanSwitch(SwitchEntity):
    """Representation of a Generic Switch."""

    def __init__(self, coordinator, name="Thermex Fan Switch"):
        """Initialize the switch."""
        self._coordinator = coordinator
        self._attr_id = "Fan_Switch"#device_id
        self._attr_name = name
        self._attr_state = False

    @property
    def unique_id(self):
        """Return a unique ID to use for this switch."""
        return f"{DOMAIN}_{self._attr_id}"

    @property
    def name(self):
        """Return the display name of this switch."""
        return self._attr_name

    @property
    def is_on(self):
        """Return true if the switch is on."""
        return self._attr_state

    async def async_turn_on(self, **kwargs):
        """Turn the switch on."""
        _LOGGER.info("Turning on the switch")
        # Add code to turn on the switch
        await self._coordinator.update_fan(fanonoff=1, fanspeed=2)
        self._attr_state = True

    async def async_turn_off(self, **kwargs):
        """Turn the switch off."""
        _LOGGER.info("Turning off the switch")
        # Add code to turn off the switch
        await self._coordinator.update_fan(fanonoff=0, fanspeed=2)
        self._attr_state = False

    async def async_update(self):
        """Update the switch's state."""
        _LOGGER.debug("Updating switch state")
        data = await self._coordinator.async_get_data()
        fan_data = data.get("Fan", {})
        fanonoff = fan_data.get("fanonoff", 0)
        if fanonoff == 1:
            self._attr_state = True
        elif fanonoff == 0:
            self._attr_state = False
        else:
            _LOGGER.warning("Unexpected value for fanonoff: %s", fanonoff)
            self._attr_state = None
