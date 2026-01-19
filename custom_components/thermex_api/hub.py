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
from .const import (
    DOMAIN,
    THERMEX_NOTIFY,
    DEFAULT_PORT,
    WEBSOCKET_PATH,
    DEFAULT_HEARTBEAT_INTERVAL,
    DEFAULT_CONNECTION_TIMEOUT,
    DEFAULT_RECONNECT_DELAY,
    MAX_RECONNECT_ATTEMPTS,
    RECONNECT_WAIT_ITERATIONS,
    WEBSOCKET_REQUEST_TIMEOUT,
)

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
        self.runtime_manager: Any = None  # Set later in __init__.py

        self._connection_state: str = "disconnected"
        self.last_status: dict | None = None
        self.last_error: str | None = None
        self.recent_messages: collections.deque = collections.deque(maxlen=10)
        self._startup_complete: bool = False

        self._reconnect_lock = asyncio.Lock()
        self._reconnect_delay = DEFAULT_RECONNECT_DELAY
        self._reconnecting = False
        self._closing = False  # Flag to prevent operations during close
        self._is_closing = False  # Additional flag for async close operations
        self._is_reconnecting = False  # Flag to prevent concurrent reconnections
        
        # Watchdog settings
        self._watchdog_task: asyncio.Task | None = None
        self._last_activity = 0.0  # Will be set properly when loop starts
        self._heartbeat_interval = DEFAULT_HEARTBEAT_INTERVAL
        self._heartbeat_lock = asyncio.Lock()  # Prevent concurrent heartbeats
        self._last_heartbeat = 0.0  # Track last heartbeat time
        self._connection_timeout = DEFAULT_CONNECTION_TIMEOUT
        self._heartbeat_in_progress = False  # Prevent concurrent heartbeats

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
        # Don't reconnect if we're closing
        if self._closing:
            raise ConnectionError("Hub is closing")
            
        if self._ws and not self._ws.closed:
            return
        
        # Check if reconnection is already in progress BEFORE acquiring lock
        if self._reconnecting or self._is_reconnecting:
            _LOGGER.debug("Reconnection already in progress, waiting...")
            # Wait for the ongoing reconnection to complete
            for _ in range(RECONNECT_WAIT_ITERATIONS):
                await asyncio.sleep(0.5)
                if self._ws and not self._ws.closed:
                    _LOGGER.debug("Connection restored by another task")
                    return
                if not (self._reconnecting or self._is_reconnecting):
                    # Reconnection finished but failed, we can try again
                    break
            else:
                # Still reconnecting after 10 seconds
                raise ConnectionError("Reconnection timeout - another task is still reconnecting")

        async with self._reconnect_lock:
            # Check again after acquiring lock
            if self._closing:
                raise ConnectionError("Hub is closing")
                
            if self._ws and not self._ws.closed:
                return  # another coroutine already reconnected

            # Final check - another task might have started reconnecting while we waited for lock
            if self._reconnecting or self._is_reconnecting:
                raise ConnectionError("Reconnection started by another task while acquiring lock")
                
            self._reconnecting = True
            self._is_reconnecting = True
            
            try:
                # Clean up old session and ws if not already done
                await self._close_connection()

                # Try to reconnect
                _LOGGER.warning("ThermexHub: WebSocket disconnected, attempting to reconnect...")
                attempt = 0
                while not self._closing:
                    try:
                        await self.connect()
                        _LOGGER.info("ThermexHub: WebSocket reconnected successfully.")
                        break
                    except Exception as err:
                        attempt += 1
                        self.last_error = f"Reconnect attempt {attempt} failed: {err}"
                        _LOGGER.error("ThermexHub: Reconnect attempt %d failed: %s", attempt, err)
                        if attempt >= MAX_RECONNECT_ATTEMPTS:
                            raise ConnectionError(f"Failed to reconnect after {attempt} attempts")
                        await asyncio.sleep(self._reconnect_delay)
                        # Optionally add a backoff strategy here
            finally:
                self._reconnecting = False
                self._is_reconnecting = False

    async def _close_connection(self) -> None:
        """Close WebSocket and session without affecting tasks."""
        if self._ws:
            try:
                await self._ws.close()
            except Exception as e:
                _LOGGER.debug("Error closing WebSocket: %s", e)
            self._ws = None
            
        if self._session:
            try:
                await self._session.close()
            except Exception as e:
                _LOGGER.debug("Error closing session: %s", e)
            self._session = None

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
        try:
            await self._ws.send_json(auth_payload)
            msg = await self._ws.receive()
        except Exception as err:
            self._connection_state = "error"
            self.last_error = f"Authentication send/receive failed: {err}"
            raise ConnectionError(f"Authentication send/receive failed: {err}")
            
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
                data = proto_resp.get("Data", {})
                # Handle both formats: {"Version": "1.1"} or {"MajorVersion": 1, "MinorVersion": 1}
                if "Version" in data:
                    self._protocol_version = data["Version"]
                elif "MajorVersion" in data and "MinorVersion" in data:
                    major = data["MajorVersion"]
                    minor = data["MinorVersion"]
                    self._protocol_version = f"{major}.{minor}"
                else:
                    self._protocol_version = "unknown"
                _LOGGER.debug("ProtocolVersion response data: %s", data)
                _LOGGER.debug("Parsed protocol version: %s", self._protocol_version)
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
        
        while not self._closing:
            try:
                await asyncio.sleep(self._heartbeat_interval)
                
                # Skip if we're closing or reconnecting
                if self._closing or self._reconnecting:
                    continue
                
                # Check if connection is still alive
                if not self._ws or self._ws.closed:
                    _LOGGER.warning("ThermexHub: Watchdog detected closed WebSocket")
                    try:
                        await self._ensure_connected()
                    except Exception as e:
                        _LOGGER.error("ThermexHub: Watchdog reconnection failed: %s", e)
                    continue
                
                current_time = asyncio.get_event_loop().time()
                time_since_activity = current_time - self._last_activity
                
                # If no activity for too long, consider connection dead
                if time_since_activity > self._connection_timeout:
                    _LOGGER.warning(
                        "ThermexHub: No activity for %.1f seconds, reconnecting...", 
                        time_since_activity
                    )
                    try:
                        await self._ensure_connected()
                    except Exception as e:
                        _LOGGER.error("ThermexHub: Timeout reconnection failed: %s", e)
                    continue
                
                # Send heartbeat (status request) to keep connection alive - but only if not already in progress
                async with self._heartbeat_lock:
                    current_time = asyncio.get_event_loop().time()
                    # Only send heartbeat if enough time has passed since last one
                    if current_time - self._last_heartbeat > self._heartbeat_interval / 2:
                        try:
                            _LOGGER.debug("ThermexHub: Sending heartbeat status request")
                            await self.send_request("status", {})
                            _LOGGER.debug("ThermexHub: Heartbeat successful")
                            self._last_heartbeat = current_time
                        except ConnectionError as err:
                            _LOGGER.warning("ThermexHub: Heartbeat failed due to connection: %s", err)
                            # Don't immediately reconnect on connection errors - let the next iteration handle it
                        except Exception as err:
                            _LOGGER.warning("ThermexHub: Heartbeat failed: %s", err)
                            # Only try to reconnect for unexpected errors, not connection issues
                    
            except asyncio.CancelledError:
                _LOGGER.debug("ThermexHub: Watchdog loop cancelled")
                break
            except Exception as err:
                _LOGGER.error("ThermexHub: Watchdog loop error: %s", err)
                await asyncio.sleep(5)  # Wait before retrying
        return

    async def send_request(self, request: str, body: Dict[str, Any]) -> Dict[str, Any]:
        """Send a JSON-RPC request and wait for its matching response, with one retry and reconnect on repeated timeout."""
        # Don't send requests if we're closing
        if self._closing:
            raise ConnectionError("Hub is closing")
            
        # Ensure websocket is open (and reconnect if not)
        try:
            await self._ensure_connected()
        except ConnectionError:
            # If we can't connect, don't try to send the request
            raise

        # Prepare future and track it by lowercase key
        loop = asyncio.get_running_loop()
        fut = loop.create_future()
        key = request.lower()
        if key in self._pending:
            _LOGGER.warning("Overwriting pending request for key %s", key)
        self._pending[key] = fut

        # Map to actual RPC request name
        req_type = _REQUEST_MAP.get(key, request)
        payload: Dict[str, Any] = {"Request": req_type}
        if req_type not in ("Status", "ProtocolVersion"):
            payload["Data"] = body

        # Send the JSON payload once before any waits
        async with self._ws_lock:
            # Double-check connection right before sending
            if self._closing:
                self._pending.pop(key, None)
                raise ConnectionError("Hub is closing")
                
            if self._ws is None or self._ws.closed:
                self._pending.pop(key, None)
                raise ConnectionError("WebSocket connection lost before sending")
            try:
                await self._ws.send_json(payload)
                # Update activity timestamp when sending
                self._last_activity = asyncio.get_event_loop().time()
                _LOGGER.debug("ThermexHub: Sent %s payload: %s", request, payload)
            except Exception as exc:
                self._pending.pop(key, None)
                raise ConnectionError(f"Failed to send WebSocket message: {exc}")

        try:
            # Try up to 2 attempts
            for attempt in (1, 2):
                try:
                    # Wait for matching response
                    return await asyncio.wait_for(fut, timeout=WEBSOCKET_REQUEST_TIMEOUT)
                except asyncio.TimeoutError:
                    # Timeout: either retry or give up (don't cascade reconnections)
                    _LOGGER.debug(
                        "ThermexHub: Timeout waiting for '%s' response (attempt %d/2)",
                        request,
                        attempt,
                    )
                    # Clean up old future
                    self._pending.pop(key, None)

                    if attempt == 1:
                        # First timeout → retry: recreate future, re-send
                        if self._closing:
                            raise ConnectionError("Hub is closing")
                            
                        fut = loop.create_future()
                        self._pending[key] = fut
                        async with self._ws_lock:
                            # Double-check connection before retry
                            if self._closing:
                                self._pending.pop(key, None)
                                raise ConnectionError("Hub is closing")
                                
                            if self._ws is None or self._ws.closed:
                                self._pending.pop(key, None)
                                raise ConnectionError("WebSocket connection lost during retry")
                            try:
                                await self._ws.send_json(payload)
                                _LOGGER.debug(
                                    "ThermexHub: Retrying %s payload: %s", request, payload
                                )
                            except Exception as exc:
                                self._pending.pop(key, None)
                                raise ConnectionError(f"Failed to retry WebSocket message: {exc}")
                        continue

                    # Second timeout → give up (don't trigger cascading reconnections)
                    _LOGGER.warning(
                        "ThermexHub: Second timeout for '%s', giving up", request
                    )
                    raise asyncio.TimeoutError(f"Request '{request}' timed out after 2 attempts")

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
            "protocol_version": self.protocol_version,
        }
    
    async def close(self) -> None:
        """Cancel receive loop and close connections."""
        self._closing = True
        self._is_closing = True
        
        # Cancel pending requests with a clear error
        for fut in list(self._pending.values()):
            if not fut.done():
                fut.set_exception(ConnectionError("Hub is closing"))
        self._pending.clear()
        
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
            
        # Close connection
        await self._close_connection()
        
        self._connection_state = "closed"
