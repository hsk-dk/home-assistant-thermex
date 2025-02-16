import aiohttp
import json
import logging
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)
DEFAULT_BRIGHTNESS = 50  # Angiv din standard lysstyrkeværdi her

class ThermexAPI:
    """Class to interact with the Thermex API."""

    def __init__(self, host, code):
        self._host = host
        self._password = code
        self._coordinator = None

    @property
    def coordinator(self):
        """Return the coordinator."""
        return self._coordinator

    async def async_setup_coordinator(self):
        """Set up data update coordinator."""
        self._coordinator = DataUpdateCoordinator(
            self._host,
            _LOGGER,
            name="thermex_data",
            update_method=self.async_get_data,
            update_interval=timedelta(seconds=10),
        )
        await self._coordinator.async_refresh()

    async def authenticate(self, websocket):
        auth_message = {
            "Request": "Authenticate",
            "Data": {"Code": self._password}
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
    
    async def fetch_status(self):
        """Fetch status of fan and light."""
        async with aiohttp.ClientSession() as session:
            async with session.ws_connect(f'ws://{self._host}:9999/api') as websocket:
                await self.authenticate(websocket)
                _LOGGER.debug("Fetching fan and light status")
                await websocket.send_json({"Request": "STATUS"})
                response = await websocket.receive()
                response = json.loads(response.data)
                _LOGGER.debug("Status response: %s", response)
                if response.get("Response") == "Status":
                    return response.get("Data")
                else:
                    _LOGGER.error("Error fetching status: %s", response)
                    raise Exception("Unexpected response from Thermex API")

    async def async_get_data(self):
        """Fetch and return status data."""
        return await self.fetch_status()

    async def get_fan_status(self):
        """Get the status of the fan."""
        async with aiohttp.ClientSession() as session:
            async with session.ws_connect(f'ws://{self._host}:9999/api') as websocket:
                if await self.authenticate(websocket):
                    _LOGGER.debug("api.py forsøger at efterspørge status")
                    await websocket.send_json({"Request": "STATUS"})
                    response = await websocket.receive()
                    response = json.loads(response.data)
                    _LOGGER.debug("api.py response fra fan_status: %s", response)
                    if response.get("Response") == "Status":
                        return response.get("Data").get("Fan")
                    else:
                        _LOGGER.error("api.py Fejl ved hentning af fan status: %s", response)
                        raise Exception("api.py Uventet svar fra Thermex API")
                else:
                    _LOGGER.error("api.py Fejl under hentning af fan status")
    
    async def update_fan(self, fanonoff, fanspeed):
        """Update fan settings."""
        async with aiohttp.ClientSession() as session:
            async with session.ws_connect(f'ws://{self._host}:9999/api') as websocket:
                if await self.authenticate(websocket):
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

    async def update_light(self, lightonoff, brightness=None):
        """Update light settings."""
        _LOGGER.debug("update_light(%s)", lightonoff)
        async with aiohttp.ClientSession() as session:
            async with session.ws_connect(f'ws://{self._host}:9999/api') as websocket:
                if await self.authenticate(websocket):
                    if brightness is None:
                        brightness = DEFAULT_BRIGHTNESS

                    update_message = {
                        "Request": "Update",
                        "Data": {
                            "light": {
                                "lightonoff": lightonoff,
                                "lightbrightness": brightness
                            }
                        }
                    }
                    _LOGGER.debug("update_msg=%s", update_message)
                    await websocket.send_json(update_message)
                    response = await websocket.receive()
                    _LOGGER.debug("Update response: %s", response.data)
                    _LOGGER.info("Update successful")
                else:
                    _LOGGER.error("Update failed due to authentication failure")
