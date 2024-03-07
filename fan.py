from homeassistant.components.fan import (
    FanEntityFeature,
    FanEntity,
)
from homeassistant.const import STATE_OFF

from .const import DOMAIN

SUPPORTED_SPEEDS = [1, 2, 3, 4]

async def async_setup_entry(hass, config_entry, async_add_entities):
    """Set up the Thermex fan platform."""
    api = hass.data[DOMAIN][config_entry.entry_id]
    fan = ThermexFan(api)
    async_add_entities([fan])

class ThermexFan(FanEntity):
    """Representation of a Thermex fan."""
    _attr_supported_features = FanEntityFeature.SET_SPEED
    def __init__(self, api):
        self._api = api
        self._attr_state = STATE_OFF
        self._speed = None
        self._is_on = None
        self._current_speed = None
        self._attr_device_info = None
        self._attr_unique_id = f"thermex_fan_{self._api.host}"
        self.entity_id = DOMAIN + "." + self._attr_unique_id


    async def async_update(self):
        """Update the fan entity."""
        try:
            status = await self._api.get_status()
            if status:
                self._is_on = status.get("Fan", {}).get("fanonoff", False)
                self._current_speed = status.get("Fan", {}).get("fanspeed", 0)
                self._speed = self._current_speed if self._is_on else None

        except Exception as e:
            _LOGGER.error(f"Failed to update fan status: {e}")

  #  @property
  #  def extra_state_attributes(self):
  #      """Return the state attributes of the battery."""
  #      attrs = {}
  #      attrs["fanonoff"] = self._is_on
  #      attrs["Speed"] = self._speed
  #      return attrs

 #   @property
 #   def device_info(self):
 #       """Return device specific attributes."""
 #       return {
 #           "identifiers": {(DOMAIN, self._api.host)},
 #           "manufacturer": "Thermex",
 #           "name": "Thermex Fan",
 #           "model": "Thermex Model NewCastel",  # Replace with actual model
 #           "via_device": (DOMAIN, self._api.host),
 #           "sw_version": f"{status.get('Data', {}).get('MajorVersion', 0)}.{status.get('Data', {}).get('MinorVersion', 0)}",
 #           }            
            
    @property
    def name(self):
        """Return the name of the fan."""
        return "Thermex Fan"

    @property
    def is_on(self):
        """Return true if the fan is on."""
        return self._is_on

    @property
    def speed(self):
        """Return the current speed."""
        return self._speed

    @property
    def unique_id(self):
        """Return a unique ID for this entity."""
        return self._attr_unique_id

    async def async_turn_on(self, speed=None, preset_mode=None, **kwargs):
        """Turn on the fan."""
        if speed is not None:
            await self._api.send_request(
                f'{{"Request": "Update", "Data": {{"fan": {{"fanonoff": 1, "fanspeed": {speed}}}}}}}'
            )
            _LOGGER.debug("Turn on with speed")
            self._speed = speed
        else:
            await self._api.send_request(
                '{"Request": "Update", "Data": {"fan": {"fanonoff": 1, "fanspeed": 1}}}'
            )
            _LOGGER.debug("Turn on without speed")
            self._speed = 1
        status = await self._api.get_status()
        self._is_on = status.get("Fan", {}).get("fanonoff", False)
        self.async_write_ha_state()
    
    async def async_turn_off(self, **kwargs):
        """Turn off the fan."""
        try:
            await self._api.send_request(
                '{"Request": "Update", "Data": {"fan": {"fanonoff": 0, "fanspeed": 1}}}'
            )
            self._is_on = False
            self._speed = None
            self.async_write_ha_state()
        except Exception as e:
            _LOGGER.error(f"Failed to turn off fan: {e}")

    async def async_set_speed(self, speed: str):
        """Set the speed of the fan."""
        try:
            await self._api.send_request(
                f'{{"Request": "Update", "Data": {{"fan": {{"fanonoff": 1, "fanspeed": {speed}}}}}}}'
            )
            self._speed = int(speed)
            self._is_on = True
            self.async_write_ha_state()
        except Exception as e:
            _LOGGER.error(f"Failed to set fan speed: {e}")

        
    async def async_set_percentage(self, percentage):
        """Set the fan speed percentage."""
        # Calculate the speed value based on the percentage
        speed = int(percentage * len(SUPPORTED_SPEEDS) / 100)
        if speed == 0:
            speed = 1  # Ensure speed is at least 1
        elif speed > len(SUPPORTED_SPEEDS):
            speed = len(SUPPORTED_SPEEDS)  # Cap speed at the maximum supported speed

        # Set the fan speed
        await self.async_set_speed(speed)
