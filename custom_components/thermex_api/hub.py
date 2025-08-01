import asyncio
import logging
from typing import Any, Dict
import collections
import json
import aiohttp
from aiohttp import WSMsgType, ClientWebSocketResponse
from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.entity import DeviceInfo
from .const import DOMAIN, THERMEX_NOTIFY, DEFAULT_PORT, WEBSOCKET_PATH

_LOGGER = logging.getLogger(__name__)

_REQUEST_MAP: Dict[str, str] = {
    "authenticate":    "Authenticate",
    "update":          "Update",
    "status":          "Status",
    "protocolversion": "ProtocolVersion",
}

class ThermexHub:
    def __init__(self, hass: HomeAssistant, host: str, api_key: str, entry_id: str):
        self._hass = hass
        self._entry_id = entry_id 
        self._host = host
        self._api_key = api_key
        self.unique_id = f"thermex_{host.replace('.', '_')}"
        self._pending: Dict[str, asyncio.Future] = {}
        self._ws_lock = asyncio.Lock()
        self._ws: ClientWebSocketResponse | None = None
        self._recv_task: asyncio.Task | None = None
        self._session: aiohttp.ClientSession | None = None
        self._protocol_version: str | None = None
        
        # Connection states: disconnected, connecting, authenticating, initializing, connected, error
        self._connection_state: str = "disconnected"
        self.last_status: dict | None = None
        self.last_error: str | None = None
        self.recent_messages = collections.deque(maxlen=10)

        self._reconnect_lock = asyncio.Lock()
        self._reconnect_delay = 2  # seconds, backoff could be added
        self._reconnecting = False

    async def _ensure_connected(self) -> None:
        """Ensure that the WebSocket connection is alive, reconnect if needed."""
        if self._ws and not self._ws.closed:
            return

        async with self._reconnect_lock:
            if self._ws and not self._ws.closed:
                return  # another coroutine already reconnected

            # Clean up old session and ws if not already done
            await self.close()

            # Try to reconnect
            _LOGGER.warning("ThermexHub: WebSocket disconnected, attempting to reconnect...")
            attempt = 0
            while True:
                try:
                    await self.connect()
                    _LOGGER.info("ThermexHub: WebSocket reconnected successfully.")
                    break
                except Exception as err:
                    attempt += 1
                    self.last_error = f"Reconnect attempt {attempt} failed: {err}"
                    _LOGGER.error("ThermexHub: Reconnect attempt %d failed: %s", attempt, err)
                    await asyncio.sleep(self._reconnect_delay)
                    # Optionally add a backoff strategy here

    async def connect(self) -> None:
        """Connect to the WebSocket, authenticate, and initialize the device."""
        # First establish the connection
        self._connection_state = "connecting"
        try:
            self._session = aiohttp.ClientSession()
            url = f"ws://{self._host}:{DEFAULT_PORT}{WEBSOCKET_PATH}"
            _LOGGER.debug("Connecting to Thermex at %s", url)
            self._ws = await self._session.ws_connect(url)
        except Exception as err:
            self._connection_state = "error"
            self.last_error = f"Connection failed: {str(err)}"
            raise

        # Then authenticate
        self._connection_state = "authenticating"
        auth_payload = {"Request": "Authenticate", "Data": {"Code": self._api_key}}
        try:
            await self._ws.send_json(auth_payload)
            msg = await self._ws.receive()
            if msg.type != WSMsgType.TEXT:
                self._connection_state = "error"
                self.last_error = "Authentication failed: no text response"
                raise ConnectionError("Authentication failed: no text response")
            data = json.loads(msg.data)
            if data.get("Response") != "Authenticate" or data.get("Status") != 200:
                _LOGGER.error("Authentication rejected: %s", data)
                self._connection_state = "error"
                self.last_error = f"Authentication failed: {data}"
                raise ConnectionError(f"Authentication failed: {data}")
            _LOGGER.debug("Authenticated successfully with Thermex (status=200)")
            self._connection_state = "initializing"
        except Exception as err:
            self._connection_state = "error"
            self.last_error = f"Authentication failed: {str(err)}"
            raise

        self._recv_task = asyncio.create_task(self._recv_loop())
        
        # Allow receive loop to start
        await asyncio.sleep(RECV_LOOP_START_DELAY)
        
        # Initialize device info and state
        await self._initialize_device()

    async def _recv_loop(self) -> None:
        assert self._ws is not None
        try:
            async for msg in self._ws:
                self.recent_messages.append(msg.data if hasattr(msg, 'data') else str(msg))
                if msg.type == WSMsgType.TEXT:
                    try:
                        payload = json.loads(msg.data)
                        if "Response" in payload:
                            key = payload["Response"].lower()
                            fut = self._pending.pop(key, None)
                            if fut and not fut.done():
                                fut.set_result(payload)
                            if payload["Response"] == "Status":
                                self.last_status = payload
                        elif "Notify" in payload:
                            ntf = payload["Notify"]
                            data = payload.get("Data", {}) or {}
                            _LOGGER.debug("Received Notify '%s': %s", ntf, data)
                            async_dispatcher_send(self._hass, THERMEX_NOTIFY, ntf, data)
                    except Exception as err:
                        self.last_error = f"Error parsing message: {err}"
                elif msg.type == WSMsgType.ERROR:
                    self.last_error = f"WebSocket error: {msg.data}"
                    _LOGGER.error("WebSocket error: %s", msg.data)
                    break
        except Exception as err:
            self._connection_state = "disconnected"
            self.last_error = f"Receive loop error: {err}"
        finally:
            self._connection_state = "disconnected"
            # Optionally, trigger reconnection or notify

    async def send_request(self, request: str, body: Dict[str, Any]) -> Dict[str, Any]:
        """Send a JSON-RPC request and wait for its matching response, with one retry and reconnect on repeated timeout."""
        # Ensure websocket is open (and reconnect if not)
        await self._ensure_connected()

        # Prepare future and track it by lowercase key
        loop = asyncio.get_running_loop()
        fut = loop.create_future()
        key = request.lower()
        if key in self._pending:
            _LOGGER.warning("Overwriting pending request for key %s", key)
        self._pending[key] = fut

        # Map to actual RPC request name
        req_type = _REQUEST_MAP.get(key, request)
        payload = {"Request": req_type}
        if req_type not in ("Status", "ProtocolVersion"):
            payload["Data"] = body

        # Send the JSON payload once before any waits
        async with self._ws_lock:
            await self._ws.send_json(payload)
            _LOGGER.debug("ThermexHub: Sent %s payload: %s", request, payload)

        try:
            # Try up to 2 attempts
            for attempt in (1, 2):
                try:
                    # Wait for matching response
                    return await asyncio.wait_for(fut, timeout=10)
                except asyncio.TimeoutError:
                    # Timeout: either retry or reconnect
                    _LOGGER.debug(
                        "ThermexHub: Timeout waiting for '%s' response (attempt %d/2)",
                        request,
                        attempt,
                    )
                    # Clean up old future
                    self._pending.pop(key, None)

                    if attempt == 1:
                        # First timeout → retry: recreate future, re-send
                        fut = loop.create_future()
                        self._pending[key] = fut
                        async with self._ws_lock:
                            await self._ws.send_json(payload)
                            _LOGGER.debug(
                                "ThermexHub: Retrying %s payload: %s", request, payload
                            )
                        continue

                    # Second timeout → reconnect once and give up
                    _LOGGER.warning(
                        "ThermexHub: Second timeout for '%s', reconnecting WebSocket...", request
                    )
                    # Tear down and re-establish connection
                    await self.close()
                    await self._ensure_connected()
                    raise

        finally:
            # Always remove pending entry (in case of success or error)
            self._pending.pop(key, None)
    async def _initialize_device(self) -> None:
        """Initialize the device by fetching protocol version and initial state."""
        max_retries = 3
        retry_delay = 2

        # First get protocol version
        for attempt in range(max_retries):
            try:
                proto_resp = await self.send_request("protocolversion", {})
                if proto_resp.get("Status") == 200:
                    self._protocol_version = proto_resp.get("Data", {}).get("Version")
                    _LOGGER.debug("ProtocolVersion response data: %s", proto_resp.get("Data"))
                    break
                else:
                    _LOGGER.error("ProtocolVersion returned non-200 status: %s", proto_resp)
            except asyncio.TimeoutError:
                _LOGGER.debug("ProtocolVersion request timeout (attempt %d/%d)", attempt + 1, max_retries)
            except Exception as err:
                _LOGGER.error("ProtocolVersion request failed (attempt %d/%d): %s", attempt + 1, max_retries, err)
            
            if attempt < max_retries - 1:
                await asyncio.sleep(retry_delay)
        
        # Then get initial state
        for attempt in range(max_retries):
            try:
                resp = await self.send_request("status", {})
                if resp.get("Status") == 200:
                    data = resp.get("Data", {}) or {}
                    for ntf_type, section in data.items():
                        _LOGGER.debug("Initial STATUS notify: %s=%s", ntf_type, section)
                        async_dispatcher_send(self._hass, THERMEX_NOTIFY, ntf_type, {ntf_type: section})
                    break
                else:
                    _LOGGER.error("Initial STATUS returned non-200 status: %s", resp)
            except asyncio.TimeoutError:
                _LOGGER.warning("Initial STATUS request timeout (attempt %d/%d)", attempt + 1, max_retries)
            except Exception as exc:
                _LOGGER.warning("Initial STATUS request failed (attempt %d/%d): %s", attempt + 1, max_retries, exc)
            
            if attempt < max_retries - 1:
                await asyncio.sleep(retry_delay)

    @property
    def name(self) -> str:
        """Return the name of the device."""
        return f"Thermex Hood ({self._host})"

    @property
    def protocol_version(self) -> str | None:
        """Return the protocol version of the device."""
        return self._protocol_version

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info."""
        return DeviceInfo(
            identifiers={(DOMAIN, self.unique_id)},
            manufacturer="Thermex",
            model=f"ESP-API ({self._host})",
            sw_version=self.protocol_version
        )

    def get_coordinator_data(self):
        runtime_manager = self.runtime_manager
        return {
            "filtertime": runtime_manager.get_filter_time(),
            "connection_state": self._connection_state,
            "last_error": self.last_error,
        }
    
    async def close(self) -> None:
        """Cancel receive loop and close connections."""
        if self._recv_task:
            self._recv_task.cancel()
            try:
                await self._recv_task
            except asyncio.CancelledError:
                pass
            self._recv_task = None
        if self._ws:
            await self._ws.close()
            self._ws = None
        if self._session:
            await self._session.close()
            self._session = None
