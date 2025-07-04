import asyncio
import json
import logging
from typing import Any, Dict

import aiohttp
from aiohttp import WSMsgType, ClientWebSocketResponse
from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import async_dispatcher_send
from .const import THERMEX_NOTIFY, DEFAULT_PORT, WEBSOCKET_PATH

_LOGGER = logging.getLogger(__name__)

# Map internal keys to API request strings
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
        # stable identifier for device grouping
        self.unique_id = f"thermex_{host.replace('.', '_')}"
        self._pending: Dict[str, asyncio.Future] = {}
        self._ws_lock = asyncio.Lock()
        self._ws: ClientWebSocketResponse | None = None
        self._recv_task: asyncio.Task | None = None
        self._session: aiohttp.ClientSession | None = None

    async def connect(self) -> None:
        """Connect and authenticate to the Thermex WebSocket API."""
        self._session = aiohttp.ClientSession()
        url = f"ws://{self._host}:{DEFAULT_PORT}{WEBSOCKET_PATH}"
        _LOGGER.debug("Connecting to Thermex at %s", url)
        self._ws = await self._session.ws_connect(url)

        # Authenticate
        auth_payload = {"Request": "Authenticate", "Data": {"Code": self._api_key}}
        await self._ws.send_json(auth_payload)
        msg = await self._ws.receive()
        if msg.type != WSMsgType.TEXT:
            raise ConnectionError("Authentication failed: no text response")
        data = json.loads(msg.data)
        if data.get("Response") != "Authenticate" or data.get("Status") != 200:
            _LOGGER.error("Authentication rejected: %s", data)
            raise ConnectionError(f"Authentication failed: {data}")
        _LOGGER.debug("Authenticated successfully with Thermex (status=200)")

        # Start receive loop *before* further RPCs
        self._recv_task = asyncio.create_task(self._recv_loop())

        # Negotiate protocol version (optional)
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

        # Dispatch an initial full STATUS so entities get startup state
        asyncio.create_task(self._dispatch_initial_status())

    async def send_request(self, request: str, body: Dict[str, Any]) -> Dict[str, Any]:
        """Send a JSON-RPC request and wait for its matching response."""
        fut = asyncio.get_running_loop().create_future()
        key = request.lower()
        self._pending[key] = fut

        req_type = _REQUEST_MAP.get(key, request)
        async with self._ws_lock:
            payload = {"Request": req_type}
            if req_type not in ("Status", "ProtocolVersion"):
                payload["Data"] = body
            await self._ws.send_json(payload)

        try:
            return await asyncio.wait_for(fut, timeout=10)
        finally:
            self._pending.pop(key, None)

    async def _dispatch_initial_status(self) -> None:
        """Fetch and dispatch the full STATUS as individual notifications."""
        # small delay to ensure entities have subscribed
        await asyncio.sleep(1)
        try:
            resp = await self.send_request("status", {})
            data = resp.get("Data", {}) or {}
            for ntf_type, section in data.items():
                _LOGGER.debug("Initial STATUS notify: %s=%s", ntf_type, section)
                async_dispatcher_send(self._hass, THERMEX_NOTIFY, ntf_type, {ntf_type: section})
        except Exception as exc:
            _LOGGER.warning("Initial STATUS request failed: %s", exc)

    async def _recv_loop(self) -> None:
        """Consume incoming WebSocket messages."""
        assert self._ws is not None
        async for msg in self._ws:
            if msg.type == WSMsgType.TEXT:
                payload = json.loads(msg.data)
                if "Response" in payload:
                    key = payload["Response"].lower()
                    fut = self._pending.pop(key, None)
                    if fut and not fut.done():
                        fut.set_result(payload)
                elif "Notify" in payload:
                    ntf = payload["Notify"]
                    data = payload.get("Data", {}) or {}
                    _LOGGER.debug("Received Notify '%s': %s", ntf, data)
                    async_dispatcher_send(self._hass, THERMEX_NOTIFY, ntf, data)
            elif msg.type == WSMsgType.ERROR:
                _LOGGER.error("WebSocket error: %s", msg.data)
                break

    async def close(self) -> None:
        """Cancel receive loop and close connections."""
        if self._recv_task:
            self._recv_task.cancel()
        if self._ws:
            await self._ws.close()
        if self._session:
            await self._session.close()