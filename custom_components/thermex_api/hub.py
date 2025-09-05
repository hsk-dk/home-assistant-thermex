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

        self._connection_state: str = "disconnected"
        self.last_status: dict | None = None
        self.last_error: str | None = None
        self.recent_messages = collections.deque(maxlen=10)
        self._startup_complete: bool = False

        self._reconnect_lock = asyncio.Lock()
        self._reconnect_delay = 2  # seconds, backoff could be added
        self._reconnecting = False
        
        # Watchdog settings
        self._watchdog_task: asyncio.Task | None = None
        self._last_activity = 0.0  # Will be set properly when loop starts
        self._heartbeat_interval = 30  # Send heartbeat every 30 seconds
        self._connection_timeout = 120  # Consider connection dead after 2 minutes of no activity

    def configure_watchdog(self, heartbeat_interval: int = 30, connection_timeout: int = 120) -> None:
        """Configure watchdog parameters.
        
        Args:
            heartbeat_interval: Seconds between heartbeat messages (default: 30)
            connection_timeout: Seconds to wait for activity before considering connection dead (default: 120)
        """
        self._heartbeat_interval = heartbeat_interval
        self._connection_timeout = connection_timeout
        _LOGGER.debug(
            "ThermexHub: Watchdog configured - heartbeat: %ds, timeout: %ds", 
            heartbeat_interval, 
            connection_timeout
        )

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
        # Initialize activity timer and reset startup flag
        self._last_activity = asyncio.get_event_loop().time()
        self._startup_complete = False
        
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
        self._watchdog_task = asyncio.create_task(self._watchdog_loop())

        try:
            proto_resp = await self.send_request("protocolversion", {})
            if proto_resp.get("Status") == 200:
                self._protocol_version = proto_resp.get("Data", {}).get("Version")
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
                # Update activity timestamp whenever we receive a message
                self._last_activity = asyncio.get_event_loop().time()
                
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

    async def _watchdog_loop(self) -> None:
        """Watchdog loop that monitors connection health and sends periodic heartbeats."""
        _LOGGER.debug("ThermexHub: Watchdog loop started")
        
        while True:
            try:
                await asyncio.sleep(self._heartbeat_interval)
                
                # Check if connection is still alive
                if not self._ws or self._ws.closed:
                    _LOGGER.warning("ThermexHub: Watchdog detected closed WebSocket")
                    await self._ensure_connected()
                    continue
                
                current_time = asyncio.get_event_loop().time()
                time_since_activity = current_time - self._last_activity
                
                # If no activity for too long, consider connection dead
                if time_since_activity > self._connection_timeout:
                    _LOGGER.warning(
                        "ThermexHub: No activity for %.1f seconds, reconnecting...", 
                        time_since_activity
                    )
                    await self._ensure_connected()
                    continue
                
                # Send heartbeat (status request) to keep connection alive
                try:
                    _LOGGER.debug("ThermexHub: Sending heartbeat status request")
                    await self.send_request("status", {})
                    _LOGGER.debug("ThermexHub: Heartbeat successful")
                except Exception as err:
                    _LOGGER.warning("ThermexHub: Heartbeat failed: %s", err)
                    await self._ensure_connected()
                    
            except asyncio.CancelledError:
                _LOGGER.debug("ThermexHub: Watchdog loop cancelled")
                break
            except Exception as err:
                _LOGGER.error("ThermexHub: Watchdog loop error: %s", err)
                await asyncio.sleep(5)  # Wait before retrying

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
            # Update activity timestamp when sending
            self._last_activity = asyncio.get_event_loop().time()
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
    async def _dispatch_initial_status(self) -> None:
        try:
            resp = await self.send_request("status", {})
            data = resp.get("Data", {}) or {}
            for ntf_type, section in data.items():
                _LOGGER.debug("Initial STATUS notify: %s=%s", ntf_type, section)
                async_dispatcher_send(self._hass, THERMEX_NOTIFY, ntf_type, {ntf_type: section})
            # Mark startup as complete after dispatching initial status
            self._startup_complete = True
            _LOGGER.debug("ThermexHub: Initial status dispatch complete")
        except Exception as exc:
            _LOGGER.warning("Initial STATUS request failed: %s", exc)

    @property
    def name(self) -> str:
        """Return the name of the device."""
        return f"Thermex Hood ({self._host})"

    @property
    def startup_complete(self) -> bool:
        """Return whether initial startup is complete."""
        return self._startup_complete

    async def request_fallback_status(self, entity_name: str) -> dict:
        """Request fallback status in a coordinated way to avoid duplicate requests."""
        _LOGGER.debug("ThermexHub: %s requesting fallback status", entity_name)
        try:
            resp = await self.send_request("status", {})
            return resp.get("Data", {}) or {}
        except Exception as exc:
            _LOGGER.error("ThermexHub: Fallback status request failed: %s", exc)
            return {}

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
        current_time = asyncio.get_event_loop().time()
        time_since_activity = current_time - self._last_activity if self._last_activity > 0 else 0
        
        runtime_manager = self.runtime_manager
        return {
            "filtertime": runtime_manager.get_filter_time(),
            "connection_state": self._connection_state,
            "last_error": self.last_error,
            "watchdog_active": self._watchdog_task is not None and not self._watchdog_task.done(),
            "time_since_activity": round(time_since_activity, 1),
            "heartbeat_interval": self._heartbeat_interval,
            "connection_timeout": self._connection_timeout,
        }
    
    async def close(self) -> None:
        """Cancel receive loop and close connections."""
        if self._watchdog_task:
            self._watchdog_task.cancel()
            try:
                await self._watchdog_task
            except asyncio.CancelledError:
                pass
            self._watchdog_task = None
            
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
