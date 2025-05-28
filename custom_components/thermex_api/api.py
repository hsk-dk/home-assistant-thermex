import asyncio
import aiohttp
import json
import logging

from .const import DOMAIN, DEFAULT_PORT, WEBSOCKET_PATH
_LOGGER = logging.getLogger(__name__)

class ThermexAuthError(Exception):
    pass

class ThermexConnectionError(Exception):
    pass

class ThermexServerError(Exception):
    pass

class ThermexAPI:
    """Handles WebSocket communication with Thermex devices."""

    def __init__(self, host, password):
        self._host = host
        self._password = password
        self._ws = None
        self._session = None
        self._connected = False

    async def connect(self, hass):
        """Establish the WebSocket connection and authenticate."""
        url = f"ws://{self._host}:{DEFAULT_PORT}{WEBSOCKET_PATH}"
        self._session = aiohttp.ClientSession()

        try:
            _LOGGER.debug("Connecting to Thermex WebSocket at %s", url)
            self._ws = await self._session.ws_connect(url, heartbeat=30)
        except Exception as e:
            _LOGGER.error("Connection to Thermex WebSocket failed: %s", e)
            raise ThermexConnectionError from e

        await self.authenticate()

    async def authenticate(self):
        """Send authentication request."""
        message = {
            "Request": "Authenticate",
            "Data": {"Code": self._password}
        }
        await self._ws.send_str(json.dumps(message))
        response = await self._ws.receive()

        if response.type != aiohttp.WSMsgType.TEXT:
            _LOGGER.error("Unexpected auth response type: %s", response.type)
            raise ThermexAuthError("Invalid auth response type")

        data = json.loads(response.data)
        if data.get("Status") != 200:
            _LOGGER.warning("Authentication failed with status: %s", data.get("Status"))
            raise ThermexAuthError("Authentication failed")

        _LOGGER.debug("Authenticated successfully with Thermex")

    async def send_request(self, request_type, data=None):
        """Send a structured request and wait for response."""
        request = {"Request": request_type}
        if data:
            request["Data"] = data
        await self._ws.send_str(json.dumps(request))

        response = await self._ws.receive()
        if response.type != aiohttp.WSMsgType.TEXT:
            raise ThermexServerError("Invalid response from server")

        parsed = json.loads(response.data)
        if parsed.get("Status") != 200:
            raise ThermexServerError(f"Request failed with status: {parsed.get('Status')}")
        return parsed

    async def get_status(self):
        """Request full device status."""
        result = await self.send_request("Status")
        return result.get("Data")

    async def listen(self):
        """Async generator that yields Notify messages from the server."""
        if not self._ws:
            raise ThermexConnectionError("WebSocket not connected")

        try:
            async for msg in self._ws:
            if msg.type == aiohttp.WSMsgType.TEXT:
            else:
                _LOGGER.warning('Unexpected message: %%s', msg)
            except aiohttp.ClientConnectionError as e:
                _LOGGER.warning('WebSocket connection lost: %%s', e)
            except Exception as e:
                _LOGGER.error('Unexpected error in WebSocket loop: %%s', e)
                data = json.loads(msg.data)
                if "Notify" in data:
                    yield data
            elif msg.type == aiohttp.WSMsgType.CLOSED:
                break
            elif msg.type == aiohttp.WSMsgType.ERROR:
                _LOGGER.error("WebSocket error: %s", msg)
                break

    async def close(self):
        """Close the WebSocket connection cleanly."""
        if self._ws:
            await self._ws.close()
        if self._session:
            await self._session.close()
        self._connected = False