import logging
from .const import DOMAIN
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers.discovery import load_platform
from .sensor import ThermexFanSensor  # Importer sensorklassen fra sensor.py
from .light import ThermexLight  # Importer sensorklassen fra sensor.py
from .api import ThermexAPI  # Importer ThermexAPI-klassen fra api.py

_LOGGER = logging.getLogger(__name__)

async def async_setup(hass: HomeAssistant, config: dict):
    """Set up the Thermex_fan component."""
    _LOGGER.debug("Setting up Thermex_api component")
    
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
    load_platform(hass, 'sensor', DOMAIN, {}, config)
    _LOGGER.debug("Thermex Fan sensor created and added to Home Assistant")
    load_platform(hass,'light', DOMAIN, {}, config)
    _LOGGER.debug("Thermex Light created and added to Home Assistant")
    load_platform(hass,'switch', DOMAIN, {}, config)
    _LOGGER.debug("Thermex Fan Switch created and added to Home Assistant")
    return True
