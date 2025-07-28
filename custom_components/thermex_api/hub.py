import asyncio
import json
from pathlib import Path
import logging
from typing import Any, Dict
import collections

import aiohttp
from aiohttp import WSMsgType, ClientWebSocketResponse
from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import async_dispatcher_send
from .const import THERMEX_NOTIFY, DEFAULT_PORT, WEBSOCKET_PATH

_LOGGER = logging.getLogger(__name__)

_REQUEST_MAP: Dict[str, str] = {
    "authenticate":    "Authenticate",
    "update":          "Update",
    "status":          "Status",
    "protocolversion": "ProtocolVersion",
}

class ThermexHub:
    def __init__(self, hass: HomeAssistant, host: str, api_key: str):
        self._hass = hass
        self._host = host
        self._api_key = api_key
        self.unique_id = f"thermex_{host.replace('.', '_')}"
        self._pending: Dict[str, asyncio.Future] = {}
        self._ws_lock = asyncio.Lock()
        self._ws: ClientWebSocketResponse | None = None
        self._recv_task: asyncio.Task | None = None
        self._session: aiohttp.ClientSession | None = None

        self._connection_state: str = "disconnected"
        self.last_status: dict | None = None
        self.last_error: str | None = None
        self.recent_messages = collections.deque(maxlen=10)

        self._reconnect_lock = asyncio.Lock()
        self._reconnect_delay = 2  # seconds, backoff could be added
        self._reconnecting = False

        self._filter_time = 0
        self._json_path = Path(hass.config.path("thermex_filtertime.json"))
        self._load_filter_time()

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
        try:
            self._session = aiohttp.ClientSession()
            url = f"ws://{self._host}:{DEFAULT_PORT}{WEBSOCKET_PATH}"
            _LOGGER.debug("Connecting to Thermex at %s", url)
            self._ws = await self._session.ws_connect(url)
            self._connection_state = "connected"
        except Exception as err:
            self._connection_state = "error"
            self.last_error = str(err)
            raise

        # Authenticate
        auth_payload = {"Request": "Authenticate", "Data": {"Code": self._api_key}}
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

        self._recv_task = asyncio.create_task(self._recv_loop())

        try:
            proto_resp = await self.send_request("protocolversion", {})
            if proto_resp.get("Status") == 200:
                _LOGGER.debug("ProtocolVersion response data: %s", proto_resp.get("Data"))
            else:
                _LOGGER.error("ProtocolVersion returned non-200 status: %s", proto_resp)
        except asyncio.TimeoutError:
            _LOGGER.debug("No ProtocolVersion response within timeout, skipping negotiation")
        except Exception as err:
            _LOGGER.error("ProtocolVersion request failed: %s", err)
            self.last_error = f"ProtocolVersion request failed: {err}"
        await asyncio.sleep(0.1)
        asyncio.create_task(self._dispatch_initial_status())

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
        """Send a JSON-RPC request and wait for its matching response, reconnecting if necessary."""
        # Ensure websocket is open (and reconnect if not)
        await self._ensure_connected()
        fut = asyncio.get_running_loop().create_future()
        key = request.lower()
        if key in self._pending:
            _LOGGER.warning("Overwriting pending request for key %s", key)
        self._pending[key] = fut

        req_type = _REQUEST_MAP.get(key, request)
        try:
            async with self._ws_lock:
                payload = {"Request": req_type}
                if req_type not in ("Status", "ProtocolVersion"):
                    payload["Data"] = body
                try:
                    await self._ws.send_json(payload)
                except aiohttp.ClientConnectionError as err:
                    _LOGGER.warning("WebSocket send failed, will attempt reconnect: %s", err)
                    self._connection_state = "disconnected"
                    await self._ensure_connected()
                    await self._ws.send_json(payload)
        except Exception as err:
            self.last_error = f"Send request error: {err}"
            self._connection_state = "error"
            raise
        try:
            return await asyncio.wait_for(fut, timeout=10)
        finally:
            self._pending.pop(key, None)

    async def _dispatch_initial_status(self) -> None:
        try:
            resp = await self.send_request("status", {})
            data = resp.get("Data", {}) or {}
            for ntf_type, section in data.items():
                _LOGGER.debug("Initial STATUS notify: %s=%s", ntf_type, section)
                async_dispatcher_send(self._hass, THERMEX_NOTIFY, ntf_type, {ntf_type: section})
        except Exception as exc:
            _LOGGER.warning("Initial STATUS request failed: %s", exc)

    def _load_filter_time(self):
        if self._json_path.exists():
            try:
                with open(self._json_path, "r") as f:
                    self._filter_time = json.load(f).get("filtertime", 0)
            except Exception as e:
                _LOGGER.error("Failed to load filter time: %s", e)
                self._filter_time = 0
        else:
            self._filter_time = 0

    def _save_filter_time(self):
        try:
            with open(self._json_path, "w") as f:
                json.dump({"filtertime": self._filter_time}, f)
        except Exception as e:
            _LOGGER.error("Failed to save filter time: %s", e)

    def reset_filter_time(self):
        self._filter_time = 0
        self._save_filter_time()

    def update_filter_time_from_runtime(self, runtime_hours: float):
        new_value = int(runtime_hours)
        if new_value != self._filter_time:
            self._filter_time = new_value
            self._save_filter_time()

    def get_coordinator_data(self):
        return {
            "filtertime": self._filter_time,
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
