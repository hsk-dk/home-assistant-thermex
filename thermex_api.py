import asyncio
import websockets
import json
import logging

_LOGGER = logging.getLogger(__name__)

class ThermexApi:
    def __init__(self, host: str, code: str):
        self.host = host
        self.port = 9999
        self.code = code
        self.websocket = None

    async def connect(self):
        try:
            url = f"ws://{self.host}:{self.port}/api"
            self.websocket = await websockets.connect(url)
            _LOGGER.debug("WebSocket connection established")
        except Exception as e:
            _LOGGER.error(f"Failed to connect to WebSocket: {e}")

    async def authenticate(self):
        try:
            auth_message = {
                "Request": "Authenticate",
                "Data": {"Code": self.code}
            }
            _LOGGER.debug("Authentication started")
            await self.websocket.send(json.dumps(auth_message))
            response = await self.websocket.recv()
            response_data = json.loads(response)
            if response_data.get("Status") == 200:
                _LOGGER.info("Authentication successful")
                return True
            else:
                _LOGGER.error("Authentication failed")
                return False
        except Exception as e:
            _LOGGER.error(f"Authentication error: {e}")
            return False

    async def send_request(self, request: str):
        if not self.websocket or self.websocket.closed:
            await self.connect()

        try:
            await self.websocket.send(request)
            response = await self.websocket.recv()
            return response
        except Exception as e:
            _LOGGER.error(f"Error sending request: {e}")
            return None

    async def get_status(self):
            request = '{"Request": "Status"}'
            response = await self.send_request(request)
            if response:
                return json.loads(response)
            else:
                _LOGGER.error("Failed to get status")
                return None

    async def close(self):
        if self.websocket:
            await self.websocket.close()
            _LOGGER.debug("WebSocket connection closed")
