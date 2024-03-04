from __future__ import annotations
import asyncio
import json
import logging

from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.helpers.typing import ConfigType
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.service import async_register_admin_service
from homeassistant.helpers import config_validation
from homeassistant.components.fan import FanEntity
import voluptuous as vol

# The domain of your component. Should be equal to the name of your component.
DOMAIN = "thermex"
_LOGGER = logging.getLogger(__name__)

CONFIG_SCHEMA = vol.Schema({
    vol.Optional(DOMAIN): {
        vol.Required("ip"): config_validation.string,
        vol.Required("code"): config_validation.string
    }
}, extra=vol.ALLOW_EXTRA)


async def authenticate(websocket,code):
    auth_message = {
        "Request": "Authenticate",
        "Data": {"Code": code}
    }
    _LOGGER.debug("Authentication started")
    await websocket.send_json(auth_message)
    response = await websocket.receive()
    response_data = json.loads(response.data)
    if response_data.get("Status") == 200:
        _LOGGER.info("Authentication successful")
        return True
    else:
        _LOGGER.error("Authentication failed")
        return False

async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the an async service example component."""
    ip_address = config.get(DOMAIN, {}).get("ip")
    code = config.get(DOMAIN, {}).get("code")
    if ip_address is None:
        _LOGGER.error("Missing IP address in configuration")
        return False
    if code is None:
        _LOGGER.error("Missing code in configuration")
        return False
    @callback
    
    async def update_light_service(hass: HomeAssistant, call: ServiceCall) -> None:
        """My second service."""
        # Extract parameters from the service call
        lightonoff = call.data.get('lightonoff')
        brightness = call.data.get('brightness')

    # Ensure parameters are provided
        if lightonoff is None or brightness is None:
            _LOGGER.error("Missing parameters: lightonoff and/or brightness")
            return
        async with async_get_clientsession(hass=hass).ws_connect(f'ws://{ip_address}:9999/api') as websocket:
            if await authenticate(websocket,code):
                update_message = {
                    "Request": "Update",
                    "Data": {
                        "light": {
                            "lightonoff": lightonoff,
                            "lightbrightness": brightness
                        }
                    }
                }
                await websocket.send_json(update_message)
                response = await websocket.receive()
                _LOGGER.debug("Update response: %s", response.data)
                _LOGGER.info("Update successful")
            else:
                _LOGGER.error("Update failed due to authentication failure")
    async def update_fan_service(hass: HomeAssistant, call: ServiceCall) -> None:
        """fan service."""
        # Extract parameters from the service call
        fanonoff = call.data.get('fanonoff')
        fanspeed = call.data.get('fanspeed')

    # Ensure parameters are provided
        if fanonoff is None or fanspeed is None:
            _LOGGER.error("Missing parameters: fanonoff and/or fanspeed")
            return
        async with async_get_clientsession(hass=hass).ws_connect(f'ws://{ip_address}:9999/api') as websocket:
            if await authenticate(websocket,code):
                update_message = {
                    "Request": "Update",
                    "Data": {
                        "fan": {
                            "fanonoff": fanonoff,
                            "fanspeed": fanspeed
                        }
                    }
                }
                await websocket.send_json(update_message)
                response = await websocket.receive()
                _LOGGER.debug("Update response: %s", response.data)
                _LOGGER.info("Update successful")
            else:
                _LOGGER.error("Update failed due to authentication failure")

    async def update_fan_service_wrapper(call: ServiceCall) -> None:
        """Wrapper for the fan service."""
        await update_fan_service(hass, call)

    async def update_light_service_wrapper(call: ServiceCall) -> None:
        """Wrapper for the second service."""
        await update_light_service(hass, call)
    
    # Register services with Home Assistant.
    hass.services.async_register(DOMAIN, 'update_light', update_light_service_wrapper)
    hass.services.async_register(DOMAIN, 'update_fan', update_fan_service_wrapper) 

    class ThermexFanEntity(FanEntity):
        """Representation of a fan."""

        def __init__(self, ip_address, code):
            self._ip_address = ip_address
            self._code = code
            self._state = None
            self._speed = None

        @property
        def name(self):
            """Return the name of the fan."""
            return "Thermex Fan"

        @property
        def is_on(self):
            """Return true if fan is on."""
            return self._state == "on"

        @property
        def speed(self):
            """Return the current speed."""
            return self._speed

        async def async_turn_on(self, speed=None, **kwargs):
            """Turn the fan on."""
            self._state = "on"
            self._speed = speed
            await update_fan_service(hass, ServiceCall(DOMAIN, 'update_fan', {'fanonoff': 'on', 'fanspeed': speed}))

        async def async_turn_off(self, **kwargs):
            """Turn the fan off."""
            self._state = "off"
            await update_fan_service(hass, ServiceCall(DOMAIN, 'update_fan', {'fanonoff': 'off'}))

        async def async_set_speed(self, speed: str, **kwargs):
            """Set the speed of the fan."""
            self._speed = speed
            await update_fan_service(hass, ServiceCall(DOMAIN, 'update_fan', {'fanspeed': speed}))

    # Create and add the fan entity to Home Assistant
    fan_entity = MyFanEntity(ip_address, code)
    hass.data[DOMAIN] = fan_entity
    await fan_entity.async_update()

    # Return boolean to indicate that initialization was successful.
    return True
