import asyncio
import collections
import json
import logging
from collections.abc import Callable
from typing import Any

import aiohttp
from aiohttp import ClientWebSocketResponse, WSMsgType
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.entity import DeviceInfo

from .const import (
    DEFAULT_CONNECTION_TIMEOUT,
    DEFAULT_HEARTBEAT_INTERVAL,
    DEFAULT_PORT,
    DEFAULT_RECONNECT_DELAY,
    DOMAIN,
    MAX_MISSED_HEARTBEATS,
    MAX_RECONNECT_ATTEMPTS,
    THERMEX_NOTIFY,
    WEBSOCKET_PATH,
    WEBSOCKET_REQUEST_TIMEOUT,
)

_LOGGER = logging.getLogger(__name__)

_REQUEST_MAP: dict[str, str] = {
    "authenticate":    "Authenticate",
    "update":          "Update",
    "status":          "Status",
    "protocolversion": "ProtocolVersion",
}

class ThermexAuthError(ConnectionError):
    """The hood rejected the API password."""


class ThermexRequestError(HomeAssistantError):
    """The hood answered an Update with an error status."""


class ThermexHub:
    def __init__(
        self,
        hass: HomeAssistant,
        host: str,
        api_key: str,
        entry_id: str,
        device_id: str | None = None,
    ):
        self._hass = hass
        self._entry_id = entry_id 
        self._host = host
        self._api_key = api_key
        # Stable id used for the device and entity unique ids. It must not depend
        # on the IP address (which can change); the config entry stores it.
        self.unique_id = device_id or f"thermex_{host.replace('.', '_')}"
        self._pending: dict[str, asyncio.Future] = {}
        # Responses are matched by name only, so allow one in-flight request per type
        self._request_locks: dict[str, asyncio.Lock] = {}
        self._ws_lock = asyncio.Lock()
        self._ws: ClientWebSocketResponse | None = None
        self._recv_task: asyncio.Task | None = None
        self._session: aiohttp.ClientSession | None = None  # HA's shared session; never closed here
        self._auth_failed = False
        # Set by the integration: called once when the hood rejects the password
        self.on_auth_failure: Callable[[], None] | None = None
        self._protocol_version: str | None = None
        self.runtime_manager: Any = None  # Set later in __init__.py

        self._connection_state: str = "disconnected"
        self.last_status: dict | None = None
        self.last_error: str | None = None
        self.recent_messages: collections.deque = collections.deque(maxlen=10)
        self._startup_complete: bool = False

        self._reconnect_lock = asyncio.Lock()
        self._reconnect_delay = DEFAULT_RECONNECT_DELAY
        self._reconnect_event = asyncio.Event()  # Signal when reconnection completes
        self._closing = False  # Flag to prevent operations during close
        
        # Watchdog settings
        self._watchdog_task: asyncio.Task | None = None
        self._last_activity = 0.0  # Will be set properly when loop starts
        self._heartbeat_interval = DEFAULT_HEARTBEAT_INTERVAL
        self._missed_heartbeats = 0  # Heartbeats in a row the hood did not answer
        self._heartbeat_lock = asyncio.Lock()  # Prevent concurrent heartbeats
        self._last_heartbeat = 0.0  # Track last heartbeat time
        self._connection_timeout = DEFAULT_CONNECTION_TIMEOUT

    @property
    def signal(self) -> str:
        """Dispatcher signal for this hood's notifications (scoped per config entry)."""
        return f"{THERMEX_NOTIFY}_{self._entry_id}"

    @property
    def availability_signal(self) -> str:
        """Dispatcher signal sent whenever the hood becomes (un)available."""
        return f"{THERMEX_NOTIFY}_availability_{self._entry_id}"

    @property
    def available(self) -> bool:
        """Whether we are connected and authenticated."""
        return self._connection_state == "connected"

    def _set_connection_state(self, state: str) -> None:
        """Change the connection state; log loss/recovery once and tell the entities."""
        was_available = self.available
        self._connection_state = state
        if was_available == self.available:
            return
        if not self._closing:
            if self.available:
                _LOGGER.info("Connection to Thermex hood %s restored", self._host)
            else:
                _LOGGER.warning(
                    "Connection to Thermex hood %s lost: %s", self._host, self.last_error or state
                )
        async_dispatcher_send(self._hass, self.availability_signal)

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
        if self._closing:
            raise ConnectionError("Hub is closing")
        if self._auth_failed:
            raise ThermexAuthError("API password was rejected; reauthentication required")
        
        if self._ws and not self._ws.closed:
            return
        
        # Try to acquire reconnection responsibility
        if self._reconnect_lock.locked():
            # Another task is reconnecting, wait for it
            await self._wait_for_reconnection()
            return
        
        async with self._reconnect_lock:
            # Double-check after acquiring lock
            if self._closing:
                raise ConnectionError("Hub is closing")
            
            if self._ws and not self._ws.closed:
                return  # Another task reconnected while we waited
            
            try:
                await self._perform_reconnection()
            finally:
                # Signal all waiting tasks that reconnection attempt completed
                self._reconnect_event.set()
                # Reset for next reconnection
                self._reconnect_event.clear()
    
    async def _wait_for_reconnection(self) -> None:
        """Wait for another task to complete reconnection."""
        _LOGGER.debug("Reconnection in progress, waiting...")
        try:
            await asyncio.wait_for(self._reconnect_event.wait(), timeout=10.0)
            if self._ws and not self._ws.closed:
                _LOGGER.debug("Connection restored by another task")
                return
            # Reconnection completed but connection still dead
            raise ConnectionError("Reconnection completed but connection failed")
        except TimeoutError:
            raise ConnectionError("Reconnection timeout - waited 10 seconds")
    
    async def _perform_reconnection(self) -> None:
        """Perform the actual reconnection with retries."""
        await self._close_connection()
        
        _LOGGER.debug("ThermexHub: WebSocket disconnected, attempting to reconnect...")
        for attempt in range(1, MAX_RECONNECT_ATTEMPTS + 1):
            if self._closing:
                raise ConnectionError("Hub closing during reconnection")
            
            try:
                await self.connect()
                _LOGGER.debug("ThermexHub: WebSocket reconnected successfully")
                return
            except ThermexAuthError:
                self._auth_failed = True
                self.last_error = "Authentication failed: API password was rejected"
                _LOGGER.error("ThermexHub: API password rejected, giving up reconnecting")
                if self.on_auth_failure:
                    self.on_auth_failure()
                raise
            except Exception as err:
                self.last_error = f"Reconnect attempt {attempt} failed: {err}"
                _LOGGER.debug("ThermexHub: Reconnect attempt %d/%d failed: %s", 
                            attempt, MAX_RECONNECT_ATTEMPTS, err)
                if attempt < MAX_RECONNECT_ATTEMPTS:
                    await asyncio.sleep(self._reconnect_delay)
        
        raise ConnectionError(f"Failed to reconnect after {MAX_RECONNECT_ATTEMPTS} attempts")

    async def _close_connection(self) -> None:
        """Close WebSocket and session without affecting tasks."""
        if self._ws:
            try:
                await self._ws.close()
            except Exception as e:
                _LOGGER.debug("Error closing WebSocket: %s", e)
            self._ws = None
            
        # The aiohttp session is Home Assistant's shared one: just drop our reference
        self._session = None

    async def connect(self) -> None:
        """Connect and authenticate; leaves no open resources on failure."""
        try:
            await self._connect()
        except BaseException:
            await self._close_connection()
            raise

    async def _cancel_recv_task(self) -> None:
        """Cancel a previous receive loop so reconnects never leave two running."""
        task = self._recv_task
        self._recv_task = None
        if task and not task.done() and task is not asyncio.current_task():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    async def _connect(self) -> None:
        # Initialize activity timer and reset startup flag
        self._last_activity = asyncio.get_event_loop().time()
        self._startup_complete = False
        await self._cancel_recv_task()
        
        try:
            self._session = async_get_clientsession(self._hass)
            url = f"ws://{self._host}:{DEFAULT_PORT}{WEBSOCKET_PATH}"
            _LOGGER.debug("Connecting to Thermex at %s", url)
            self._ws = await self._session.ws_connect(url)
        except Exception as err:
            self.last_error = str(err)
            self._set_connection_state("error")
            raise

        # Authenticate
        auth_payload = {"Request": "Authenticate", "Data": {"Code": self._api_key}}
        try:
            await self._ws.send_json(auth_payload)
            msg = await self._ws.receive()
        except Exception as err:
            self._set_connection_state("error")
            self.last_error = f"Authentication send/receive failed: {err}"
            raise ConnectionError(f"Authentication send/receive failed: {err}")
            
        if msg.type != WSMsgType.TEXT:
            self._set_connection_state("error")
            self.last_error = "Authentication failed: no text response"
            raise ConnectionError("Authentication failed: no text response")
        data = json.loads(msg.data)
        if data.get("Response") != "Authenticate" or data.get("Status") != 200:
            _LOGGER.debug("Authentication rejected: %s", data)
            self._set_connection_state("error")
            self.last_error = f"Authentication failed: {data}"
            # Only 401 (unauthorized) means the password is wrong; 400/500 are
            # protocol or device errors and must not start a reauth prompt.
            if data.get("Response") == "Authenticate" and data.get("Status") == 401:
                raise ThermexAuthError(f"Authentication failed: {data}")
            raise ConnectionError(f"Authentication failed: {data}")
        _LOGGER.debug("Authenticated successfully with Thermex (status=200)")
        self._set_connection_state("connected")

        self._recv_task = self._hass.async_create_background_task(
            self._recv_loop(), f"{DOMAIN}_recv_{self._entry_id}"
        )
        # Reconnects call connect() again (even from the watchdog itself): keep one watchdog
        if self._watchdog_task is None or self._watchdog_task.done():
            self._watchdog_task = self._hass.async_create_background_task(
                self._watchdog_loop(), f"{DOMAIN}_watchdog_{self._entry_id}"
            )

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
        except TimeoutError:
            _LOGGER.debug("No ProtocolVersion response within timeout, skipping negotiation")
        except Exception as err:
            _LOGGER.error("ProtocolVersion request failed: %s", err)
            self.last_error = f"ProtocolVersion request failed: {err}"
        await asyncio.sleep(0.1)
        self._hass.async_create_background_task(
            self._dispatch_initial_status(), f"{DOMAIN}_initial_status_{self._entry_id}"
        )

    async def _recv_loop(self) -> None:
        assert self._ws is not None
        ws = self._ws
        errored = False
        try:
            async for msg in ws:
                # Update activity timestamp whenever we receive a message
                self._last_activity = asyncio.get_event_loop().time()

                self.recent_messages.append(msg.data if hasattr(msg, "data") else str(msg))
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

                                data = payload.get("Data", {}) or {}
                                for ntf_type, section in data.items():
                                    _LOGGER.debug("Status update dispatch: %s=%s", ntf_type, section)
                                    async_dispatcher_send(
                                        self._hass,
                                        self.signal,
                                        ntf_type,
                                        {ntf_type: section},
                                    )

                        elif "Notify" in payload:
                            ntf = payload["Notify"]
                            data = payload.get("Data", {}) or {}
                            _LOGGER.debug("Received Notify '%s': %s", ntf, data)
                            async_dispatcher_send(self._hass, self.signal, ntf, data)

                    except Exception as err:
                        self.last_error = f"Error parsing message: {err}"

                elif msg.type == WSMsgType.ERROR:
                    self.last_error = f"WebSocket error: {msg.data}"
                    errored = True
                    _LOGGER.debug("WebSocket error: %s", msg.data)
                    break

        except Exception as err:
            self.last_error = f"Receive loop error: {err}"
        else:
            if not errored and not self._closing:
                # The stream ended: the hood (or the network) closed the connection.
                # Record how, so the "connection lost" warning says why.
                exc = ws.exception()
                self.last_error = (
                    f"Connection closed by the hood (close code {ws.close_code})"
                    + (f": {exc}" if exc else "")
                )
        finally:
            self._set_connection_state("disconnected")
            # Reconnect right away instead of waiting for the next watchdog tick,
            # unless we are shutting down or a reconnect already replaced this socket.
            if ws is self._ws and not self._closing:
                self._hass.async_create_background_task(
                    self._reconnect_now(), f"{DOMAIN}_reconnect_{self._entry_id}"
                )

    async def _reconnect_now(self) -> None:
        """Reconnect immediately after the connection was closed."""
        try:
            await self._ensure_connected()
        except Exception as err:
            _LOGGER.debug("Immediate reconnect failed, the watchdog will retry: %s", err)

    async def _reconnect_dead_connection(self, reason: str) -> None:
        """The socket looks open but the hood is gone (power cut, network): start over.

        A dead peer sends no close frame, so the socket stays "open" and the entities would
        keep showing the last state. Mark the hood unavailable, drop the socket and reconnect.
        """
        self._missed_heartbeats = 0
        self.last_error = reason
        self._set_connection_state("disconnected")
        try:
            await self._close_connection()
            await self._ensure_connected()
        except Exception as err:
            _LOGGER.debug("ThermexHub: Reconnecting a dead connection failed: %s", err)

    async def _watchdog_loop(self) -> None:
        """Watchdog loop that monitors connection health and sends periodic heartbeats."""
        _LOGGER.debug("ThermexHub: Watchdog loop started")
        
        while not self._closing:
            try:
                await asyncio.sleep(self._heartbeat_interval)
                
                # Skip if we're closing or reconnecting
                if self._closing or self._reconnect_lock.locked():
                    continue
                
                # Check if connection is still alive
                if not self._ws or self._ws.closed:
                    _LOGGER.debug("ThermexHub: Watchdog detected closed WebSocket")
                    try:
                        await self._ensure_connected()
                    except Exception as e:
                        _LOGGER.debug("ThermexHub: Watchdog reconnection failed: %s", e)
                    continue
                
                current_time = asyncio.get_event_loop().time()
                time_since_activity = current_time - self._last_activity
                
                # If no activity for too long, consider connection dead
                if time_since_activity > self._connection_timeout:
                    _LOGGER.warning(
                        "ThermexHub: No activity for %.1f seconds, reconnecting...", 
                        time_since_activity
                    )
                    await self._reconnect_dead_connection(
                        f"No activity from the hood for {time_since_activity:.0f} seconds"
                    )
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
                            self._missed_heartbeats = 0
                        except ConnectionError as err:
                            _LOGGER.debug("ThermexHub: Heartbeat failed due to connection: %s", err)
                            # Don't immediately reconnect on connection errors - let the next iteration handle it
                        except Exception as err:
                            _LOGGER.warning("ThermexHub: Heartbeat failed: %s", err)
                            self._missed_heartbeats += 1
                            if self._missed_heartbeats >= MAX_MISSED_HEARTBEATS:
                                await self._reconnect_dead_connection(
                                    f"The hood did not answer {self._missed_heartbeats} heartbeats in a row"
                                )

            except asyncio.CancelledError:
                _LOGGER.debug("ThermexHub: Watchdog loop cancelled")
                break
            except Exception as err:
                _LOGGER.error("ThermexHub: Watchdog loop error: %s", err)
                await asyncio.sleep(5)  # Wait before retrying

    async def send_request(self, request: str, body: dict[str, Any]) -> dict[str, Any]:
        """Send a request and wait for its matching response.

        Responses carry no request id and are matched by name, so concurrent
        requests of the same type are queued instead of overwriting each other.
        """
        if self._closing:
            raise ConnectionError("Hub is closing")
        lock = self._request_locks.setdefault(request.lower(), asyncio.Lock())
        async with lock:
            return await self._send_request(request, body)

    async def _send_request(self, request: str, body: dict[str, Any]) -> dict[str, Any]:
        """Send a request and wait for its response, with one retry on timeout."""
        if self._closing:
            raise ConnectionError("Hub is closing")

        # Ensure websocket is open (and reconnect if not)
        # If we can't connect, ConnectionError propagates and nothing is sent
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
        payload: dict[str, Any] = {"Request": req_type}
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
                # Only what the hood sends counts as activity (see _recv_loop): a hood that
                # lost power accepts our heartbeats into the socket buffer but never answers.
                await self._ws.send_json(payload)
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
                except TimeoutError:
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
                    raise TimeoutError(f"Request '{request}' timed out after 2 attempts")
            
            # This should never be reached, but satisfies mypy
            raise RuntimeError(f"Unexpected exit from retry loop for request '{request}'")

        finally:
            # Always remove pending entry (in case of success or error)
            self._pending.pop(key, None)
    async def send_update(self, body: dict[str, Any]) -> dict[str, Any]:
        """Send an Update, require a 200 reply, then read the real state back.

        The hood answers 200 even when it clamped or rewrote a value (e.g.
        brightness 255 becomes 100, 0 turns the light off), so the entities must
        not assume their command was applied as sent. The Status read-back is
        dispatched to the entities by the receive loop.
        """
        resp = await self.send_request("Update", body)
        status = resp.get("Status")
        if status != 200:
            if await self._fan_update_applied(body):
                _LOGGER.debug(
                    "Update %s answered status %s but the hood applied it", body, status
                )
                return resp
            _LOGGER.debug("Update %s rejected with status %s", body, status)
            raise ThermexRequestError(
                translation_domain=DOMAIN,
                translation_key="request_rejected",
                translation_placeholders={"status": str(status)},
            )
        try:
            await self.send_request("status", {})
        except Exception as err:
            # Not fatal: the 30 s heartbeat will refresh the state anyway
            _LOGGER.debug("Status read-back after update failed: %s", err)
        return resp

    async def _fan_update_applied(self, body: dict[str, Any]) -> bool:
        """Tell whether a fan Update the hood answered with an error was applied anyway.

        The hood answers status 400 to every Update that turns the fan on or
        changes its speed, but carries the command out. Only the fan is checked
        this way: for anything else an error status is taken at its word.
        """
        fan = body.get("Fan")
        if set(body) != {"Fan"} or not isinstance(fan, dict):
            return False
        try:
            resp = await self.send_request("status", {})
        except Exception as err:
            _LOGGER.debug("Status read-back after a rejected fan update failed: %s", err)
            return False
        state = (resp.get("Data") or {}).get("Fan")
        if not isinstance(state, dict):
            return False
        return all(state.get(key) == value for key, value in fan.items())

    async def _dispatch_initial_status(self) -> None:
        try:
            resp = await self.send_request("status", {})
            data = resp.get("Data", {}) or {}
            for ntf_type, section in data.items():
                _LOGGER.debug("Initial STATUS notify: %s=%s", ntf_type, section)
                async_dispatcher_send(self._hass, self.signal, ntf_type, {ntf_type: section})
            # Mark startup as complete after dispatching initial status
            self._startup_complete = True
            _LOGGER.debug("ThermexHub: Initial status dispatch complete")
        except Exception as exc:
            _LOGGER.warning("Initial STATUS request failed: %s", exc)

    @property
    def name(self) -> str:
        """Return the name of the device."""
        return "Thermex Hood"

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
            name="Thermex Hood",
            model="ESP-API",
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
        
        self._set_connection_state("closed")
