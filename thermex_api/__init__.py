"""Module for Thermex api"""
import logging
from homeassistant.core import HomeAssistant,  ServiceCall
from .sensor import ThermexFanSensor  # Importer sensorklassen fra sensor.py
from .light import ThermexLight  # Importer sensorklassen fra sensor.py
from .api import ThermexAPI  # Importer ThermexAPI-klassen fra api.py
from .const import DOMAIN
_LOGGER = logging.getLogger(__name__)

async def async_setup(hass: HomeAssistant, config: dict):
    """Set up the Thermex_fan component."""
    _LOGGER.debug("Setting up Thermex_fan component")

    # Hent konfigurationsoplysninger
    conf = config.get(DOMAIN)
    host = conf.get("host")
    password = conf.get("password")

    # Opret API-instansen
    api = ThermexAPI(host, password)

    # Authenticate med API
    hass.data[DOMAIN] = api
    _LOGGER.debug("API created and saved in hass.data")

    async def update_light_service(call: ServiceCall):
        """Update light service."""
        # Extract parameters from the service call
        lightonoff = call.data.get('lightonoff')
        brightness = call.data.get('brightness')

        # Ensure parameters are provided
        if lightonoff is None or brightness is None:
            _LOGGER.error("Missing parameters: lightonoff and/or brightness")
            return

        # Perform the update action
        await api.update_light(lightonoff, brightness)

    async def update_fan_service(call: ServiceCall):
        """Update fan service."""
        # Extract parameters from the service call
        fanonoff = call.data.get('fanonoff')
        fanspeed = call.data.get('fanspeed')

        # Ensure parameters are provided
        if fanonoff is None or fanspeed is None:
            _LOGGER.error("Missing parameters: fanonoff and/or fanspeed")
            return

        # Perform the update action
        await api.update_fan(fanonoff, fanspeed)

    # Register services with Home Assistant
    hass.services.async_register(DOMAIN, 'update_light', update_light_service)
    hass.services.async_register(DOMAIN, 'update_fan', update_fan_service)

    # Opret og tilføj sensoren
    hass.helpers.discovery.load_platform('sensor', DOMAIN, {}, config)
    hass.helpers.discovery.load_platform('light', DOMAIN, {}, config)
    _LOGGER.debug("Fan sensor created and added to Home Assistant")

    return True
