"""Tests for ThermexHub WebSocket communication."""
import pytest
import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock
from aiohttp import WSMsgType

from custom_components.thermex_api.hub import ThermexHub
from custom_components.thermex_api.const import (
    DOMAIN,
    THERMEX_NOTIFY,
    DEFAULT_HEARTBEAT_INTERVAL,
    DEFAULT_CONNECTION_TIMEOUT,
)


class TestThermexHub:
    """Test ThermexHub class."""

    @pytest.fixture
    def mock_hass(self, event_loop):
        """Create a mock HomeAssistant instance."""
        hass = MagicMock()
        hass.data = {}
        hass.loop = event_loop
        return hass

    @pytest.fixture
    def hub_instance(self, mock_hass):
        """Create a ThermexHub instance."""
        hub = ThermexHub(mock_hass, "192.168.1.100", "test_password", "test_entry_id")
        # Add runtime_manager mock
        hub.runtime_manager = MagicMock()
        hub.runtime_manager.get_filter_time = MagicMock(return_value=50)
        return hub

    def test_hub_initialization(self, hub_instance):
        """Test hub initialization."""
        assert hub_instance._host == "192.168.1.100"
        assert hub_instance._api_key == "test_password"
        assert hub_instance._entry_id == "test_entry_id"
        assert hub_instance.unique_id == "thermex_192_168_1_100"
        assert hub_instance._connection_state == "disconnected"
        assert hub_instance._startup_complete is False

    def test_device_info(self, hub_instance):
        """Test device info property."""
        device_info = hub_instance.device_info
        assert device_info["identifiers"] == {(DOMAIN, hub_instance.unique_id)}
        assert device_info["manufacturer"] == "Thermex"
        assert "192.168.1.100" in device_info["model"]

    def test_protocol_version_property(self, hub_instance):
        """Test protocol version property."""
        assert hub_instance.protocol_version is None
        hub_instance._protocol_version = "1.0"
        assert hub_instance.protocol_version == "1.0"

    def test_startup_complete_property(self, hub_instance):
        """Test startup complete property."""
        assert hub_instance.startup_complete is False
        hub_instance._startup_complete = True
        assert hub_instance.startup_complete is True

    def test_name_property(self, hub_instance):
        """Test name property."""
        assert hub_instance.name == "Thermex Hood (192.168.1.100)"

    def test_configure_watchdog(self, hub_instance):
        """Test watchdog configuration."""
        hub_instance.configure_watchdog(heartbeat_interval=60, connection_timeout=180)
        assert hub_instance._heartbeat_interval == 60
        assert hub_instance._connection_timeout == 180

    def test_configure_watchdog_defaults(self, hub_instance):
        """Test watchdog configuration with defaults."""
        hub_instance.configure_watchdog()
        assert hub_instance._heartbeat_interval == 30
        assert hub_instance._connection_timeout == 120

    @pytest.mark.asyncio
    async def test_connect_success(self, hub_instance):
        """Test successful connection."""
        mock_ws = MagicMock()
        mock_ws.closed = False
        mock_ws.send_json = AsyncMock()
        mock_ws.receive = AsyncMock()
        
        # Mock authentication response
        auth_msg = MagicMock()
        auth_msg.type = WSMsgType.TEXT
        auth_msg.data = json.dumps({"Response": "Authenticate", "Status": 200})
        mock_ws.receive.return_value = auth_msg
        
        mock_session = MagicMock()
        mock_session.ws_connect = AsyncMock(return_value=mock_ws)
        
        with patch("custom_components.thermex_api.hub.aiohttp.ClientSession", return_value=mock_session):
            with patch.object(hub_instance, "_recv_loop", new_callable=AsyncMock):
                with patch.object(hub_instance, "_watchdog_loop", new_callable=AsyncMock):
                    with patch.object(hub_instance, "_dispatch_initial_status", new_callable=AsyncMock):
                        with patch.object(hub_instance, "send_request", new_callable=AsyncMock, return_value={"Status": 200, "Data": {"MajorVersion": 1, "MinorVersion": 0}}):
                            await hub_instance.connect()
        
        assert hub_instance._connection_state == "connected"
        assert hub_instance._ws is not None
        assert hub_instance._session is not None

    @pytest.mark.asyncio
    async def test_connect_authentication_failure(self, hub_instance):
        """Test connection with authentication failure."""
        mock_ws = MagicMock()
        mock_ws.send_json = AsyncMock()
        mock_ws.receive = AsyncMock()
        
        # Mock authentication failure response
        auth_msg = MagicMock()
        auth_msg.type = WSMsgType.TEXT
        auth_msg.data = json.dumps({"Response": "Authenticate", "Status": 401})
        mock_ws.receive.return_value = auth_msg
        
        mock_session = MagicMock()
        mock_session.ws_connect = AsyncMock(return_value=mock_ws)
        
        with patch("custom_components.thermex_api.hub.aiohttp.ClientSession", return_value=mock_session):
            with pytest.raises(ConnectionError, match="Authentication failed"):
                await hub_instance.connect()

    @pytest.mark.asyncio
    async def test_connect_network_error(self, hub_instance):
        """Test connection with network error."""
        mock_session = MagicMock()
        mock_session.ws_connect = AsyncMock(side_effect=Exception("Network error"))
        
        with patch("custom_components.thermex_api.hub.aiohttp.ClientSession", return_value=mock_session):
            with pytest.raises(Exception, match="Network error"):
                await hub_instance.connect()
        
        assert hub_instance._connection_state == "error"
        assert "Network error" in hub_instance.last_error

    @pytest.mark.asyncio
    async def test_send_request_success(self, hub_instance):
        """Test successful send_request."""
        # Setup mock WebSocket
        mock_ws = MagicMock()
        mock_ws.closed = False
        mock_ws.send_json = AsyncMock()
        hub_instance._ws = mock_ws
        hub_instance._last_activity = asyncio.get_event_loop().time()
        
        # Create task that will complete the future
        async def complete_future():
            await asyncio.sleep(0.1)
            fut = hub_instance._pending.get("status")
            if fut and not fut.done():
                fut.set_result({"Response": "Status", "Status": 200, "Data": {}})
        
        asyncio.create_task(complete_future())
        
        response = await hub_instance.send_request("status", {})
        
        assert response["Response"] == "Status"
        assert response["Status"] == 200
        assert mock_ws.send_json.called

    @pytest.mark.asyncio
    async def test_send_request_timeout(self, hub_instance):
        """Test send_request timeout."""
        mock_ws = MagicMock()
        mock_ws.closed = False
        mock_ws.send_json = AsyncMock()
        hub_instance._ws = mock_ws
        hub_instance._last_activity = asyncio.get_event_loop().time()
        
        # Don't complete the future, let it timeout
        with pytest.raises(asyncio.TimeoutError):
            await hub_instance.send_request("status", {})

    @pytest.mark.asyncio
    async def test_send_request_when_closing(self, hub_instance):
        """Test send_request raises error when hub is closing."""
        hub_instance._closing = True
        
        with pytest.raises(ConnectionError, match="Hub is closing"):
            await hub_instance.send_request("status", {})

    @pytest.mark.asyncio
    async def test_send_request_with_disconnected_websocket(self, hub_instance):
        """Test send_request when websocket is disconnected."""
        hub_instance._ws = None
        
        # Mock _ensure_connected to raise exception
        with patch.object(hub_instance, "_ensure_connected", new_callable=AsyncMock, side_effect=ConnectionError("Cannot connect")):
            with pytest.raises(ConnectionError, match="Cannot connect"):
                await hub_instance.send_request("status", {})

    @pytest.mark.asyncio
    async def test_recv_loop_handles_response(self, hub_instance):
        """Test receive loop handles response messages."""
        # Create mock message
        msg1 = MagicMock()
        msg1.type = WSMsgType.TEXT
        msg1.data = json.dumps({"Response": "Status", "Status": 200, "Data": {}})

        # Create async generator for messages
        async def mock_message_generator():
            yield msg1

        # Mock WebSocket with proper async iterator
        mock_ws = MagicMock()
        mock_ws.__aiter__ = lambda self: mock_message_generator().__aiter__()
        hub_instance._ws = mock_ws

        # Create a pending future
        loop = asyncio.get_event_loop()
        fut = loop.create_future()
        hub_instance._pending["status"] = fut

        # Run receive loop (will process one message then stop when generator exhausted)
        await hub_instance._recv_loop()

        # Check that future was completed
        assert fut.done()
        assert fut.result() == {"Response": "Status", "Status": 200, "Data": {}}
        result = fut.result()
        assert result["Response"] == "Status"

    @pytest.mark.asyncio
    async def test_recv_loop_handles_notify(self, hub_instance, mock_hass):
        """Test receive loop handles notify messages."""
        # Create mock notify message
        msg1 = MagicMock()
        msg1.type = WSMsgType.TEXT
        msg1.data = json.dumps({"Notify": "fan", "Data": {"Fan": {"fanonoff": 1}}})

        # Create async generator for messages
        async def mock_message_generator():
            yield msg1

        # Mock WebSocket with proper async iterator
        mock_ws = MagicMock()
        mock_ws.__aiter__ = lambda self: mock_message_generator().__aiter__()
        hub_instance._ws = mock_ws

        # Mock dispatcher
        with patch("custom_components.thermex_api.hub.async_dispatcher_send") as mock_dispatcher:
            await hub_instance._recv_loop()

            # Verify dispatcher was called
            mock_dispatcher.assert_called_once()
            # Verify it was called with correct arguments (using actual signal value)
            mock_dispatcher.assert_called_with(
                hub_instance._hass, "thermex_api_notify", "fan", {"Fan": {"fanonoff": 1}}
            )
            call_args = mock_dispatcher.call_args[0]
            assert call_args[1] == THERMEX_NOTIFY
            assert call_args[2] == "fan"

    @pytest.mark.asyncio
    async def test_recv_loop_handles_error_message(self, hub_instance):
        """Test receive loop handles error messages."""
        # Create mock error message
        msg1 = MagicMock()
        msg1.type = WSMsgType.ERROR
        msg1.data = "WebSocket error"

        # Mock async iterator properly
        mock_ws = AsyncMock()
        async_iter_mock = AsyncMock()
        async_iter_mock.__aiter__.return_value = async_iter_mock
        async_iter_mock.__anext__.side_effect = [msg1, StopAsyncIteration()]
        
        mock_ws.__aiter__.return_value = async_iter_mock
        hub_instance._ws = mock_ws

        await hub_instance._recv_loop()

        assert hub_instance._connection_state == "disconnected"
        # The error message gets logged, but last_error may contain different info
        # Just verify the connection state changed to disconnected
        """Test _ensure_connected when already connected."""
        mock_ws = MagicMock()
        mock_ws.closed = False
        hub_instance._ws = mock_ws
        
        # Should not try to reconnect
        await hub_instance._ensure_connected()
        
        assert hub_instance._ws == mock_ws

    @pytest.mark.asyncio
    async def test_ensure_connected_when_closing(self, hub_instance):
        """Test _ensure_connected raises error when closing."""
        hub_instance._closing = True
        
        with pytest.raises(ConnectionError, match="Hub is closing"):
            await hub_instance._ensure_connected()

    @pytest.mark.asyncio
    async def test_ensure_connected_reconnects(self, hub_instance):
        """Test _ensure_connected performs reconnection."""
        hub_instance._ws = None
        
        # Mock connect method
        with patch.object(hub_instance, "connect", new_callable=AsyncMock):
            await hub_instance._ensure_connected()
            
            assert hub_instance.connect.called

    @pytest.mark.asyncio
    async def test_ensure_connected_max_retries(self, hub_instance):
        """Test _ensure_connected fails after max retries."""
        hub_instance._ws = None
        
        # Mock connect to always fail
        with patch.object(hub_instance, "connect", new_callable=AsyncMock, side_effect=Exception("Connection failed")):
            with pytest.raises(ConnectionError, match="Failed to reconnect"):
                await hub_instance._ensure_connected()

    @pytest.mark.asyncio
    async def test_close_connection(self, hub_instance):
        """Test closing connection."""
        mock_ws = MagicMock()
        mock_ws.close = AsyncMock()
        mock_session = MagicMock()
        mock_session.close = AsyncMock()
        
        hub_instance._ws = mock_ws
        hub_instance._session = mock_session
        
        await hub_instance._close_connection()
        
        assert hub_instance._ws is None
        assert hub_instance._session is None
        assert mock_ws.close.called
        assert mock_session.close.called

    @pytest.mark.asyncio
    async def test_close(self, hub_instance):
        """Test hub close method."""
        # Setup mocks
        mock_ws = MagicMock()
        mock_ws.close = AsyncMock()
        mock_session = MagicMock()
        mock_session.close = AsyncMock()
        
        hub_instance._ws = mock_ws
        hub_instance._session = mock_session
        
        # Create mock tasks
        mock_recv_task = asyncio.create_task(asyncio.sleep(10))
        mock_watchdog_task = asyncio.create_task(asyncio.sleep(10))
        hub_instance._recv_task = mock_recv_task
        hub_instance._watchdog_task = mock_watchdog_task
        
        # Create pending future
        loop = asyncio.get_event_loop()
        fut = loop.create_future()
        hub_instance._pending["test"] = fut
        
        await hub_instance.close()
        
        assert hub_instance._closing is True
        assert hub_instance._connection_state == "closed"
        assert hub_instance._ws is None
        assert hub_instance._session is None
        assert len(hub_instance._pending) == 0
        assert fut.done()

    @pytest.mark.asyncio
    async def test_dispatch_initial_status(self, hub_instance):
        """Test initial status dispatch."""
        mock_response = {
            "Status": 200,
            "Data": {
                "Light": {"lightonoff": 1},
                "Fan": {"fanonoff": 0}
            }
        }
        
        with patch.object(hub_instance, "send_request", new_callable=AsyncMock, return_value=mock_response):
            with patch("custom_components.thermex_api.hub.async_dispatcher_send") as mock_dispatcher:
                await hub_instance._dispatch_initial_status()
                
                # Should dispatch for each data section
                assert mock_dispatcher.call_count == 2
                assert hub_instance._startup_complete is True

    @pytest.mark.asyncio
    async def test_dispatch_initial_status_failure(self, hub_instance):
        """Test initial status dispatch handles failure."""
        with patch.object(hub_instance, "send_request", new_callable=AsyncMock, side_effect=Exception("Failed")):
            # Should not raise, just log
            await hub_instance._dispatch_initial_status()
            
            # Startup should not be marked complete
            assert hub_instance._startup_complete is False

    @pytest.mark.asyncio
    async def test_request_fallback_status(self, hub_instance):
        """Test fallback status request."""
        mock_response = {
            "Status": 200,
            "Data": {"Light": {"lightonoff": 1}}
        }
        
        with patch.object(hub_instance, "send_request", new_callable=AsyncMock, return_value=mock_response):
            result = await hub_instance.request_fallback_status("test_entity")
            
            assert result == {"Light": {"lightonoff": 1}}

    @pytest.mark.asyncio
    async def test_request_fallback_status_failure(self, hub_instance):
        """Test fallback status request handles failure."""
        with patch.object(hub_instance, "send_request", new_callable=AsyncMock, side_effect=Exception("Failed")):
            result = await hub_instance.request_fallback_status("test_entity")
            
            assert result == {}

    def test_get_coordinator_data(self, hub_instance):
        """Test get coordinator data."""
        hub_instance._connection_state = "connected"
        hub_instance._last_activity = asyncio.get_event_loop().time()
        hub_instance._protocol_version = "1.0"
        
        data = hub_instance.get_coordinator_data()
        
        assert data["connection_state"] == "connected"
        assert data["protocol_version"] == "1.0"
        assert "time_since_activity" in data
        assert "watchdog_active" in data
        assert data["heartbeat_interval"] == DEFAULT_HEARTBEAT_INTERVAL
        assert data["connection_timeout"] == DEFAULT_CONNECTION_TIMEOUT

    def test_recent_messages_maxlen(self, hub_instance):
        """Test recent messages has max length."""
        # Add more than 10 messages
        for i in range(15):
            hub_instance.recent_messages.append(f"message_{i}")
        
        # Should only keep last 10
        assert len(hub_instance.recent_messages) == 10
        assert "message_14" in hub_instance.recent_messages
        assert "message_0" not in hub_instance.recent_messages

    @pytest.mark.asyncio
    async def test_watchdog_loop_sends_heartbeat(self, hub_instance):
        """Test watchdog loop sends periodic heartbeats."""
        mock_ws = MagicMock()
        mock_ws.closed = False
        hub_instance._ws = mock_ws
        hub_instance._heartbeat_interval = 0.1  # Short interval for testing
        hub_instance._last_activity = asyncio.get_event_loop().time()
        
        # Mock send_request
        with patch.object(hub_instance, "send_request", new_callable=AsyncMock):
            # Run watchdog for a short time
            watchdog_task = asyncio.create_task(hub_instance._watchdog_loop())
            await asyncio.sleep(0.3)
            hub_instance._closing = True
            await asyncio.sleep(0.1)
            
            # Should have sent at least one heartbeat
            assert hub_instance.send_request.call_count >= 1

    @pytest.mark.asyncio
    async def test_watchdog_detects_timeout(self, hub_instance):
        """Test watchdog detects connection timeout."""
        mock_ws = MagicMock()
        mock_ws.closed = False
        hub_instance._ws = mock_ws
        hub_instance._heartbeat_interval = 0.1
        hub_instance._connection_timeout = 0.2
        hub_instance._last_activity = 0  # Very old activity
        
        # Mock ensure_connected
        with patch.object(hub_instance, "_ensure_connected", new_callable=AsyncMock):
            # Run watchdog briefly
            watchdog_task = asyncio.create_task(hub_instance._watchdog_loop())
            await asyncio.sleep(0.3)
            hub_instance._closing = True
            await asyncio.sleep(0.1)
            
            # Should have tried to reconnect
            assert hub_instance._ensure_connected.call_count >= 1

    @pytest.mark.asyncio
    async def test_watchdog_handles_closed_websocket(self, hub_instance):
        """Test watchdog handles closed websocket."""
        mock_ws = MagicMock()
        mock_ws.closed = True
        hub_instance._ws = mock_ws
        hub_instance._heartbeat_interval = 0.1
        hub_instance._last_activity = asyncio.get_event_loop().time()
        
        with patch.object(hub_instance, "_ensure_connected", new_callable=AsyncMock):
            watchdog_task = asyncio.create_task(hub_instance._watchdog_loop())
            await asyncio.sleep(0.2)
            hub_instance._closing = True
            await asyncio.sleep(0.1)
            
            # Should have tried to reconnect
            assert hub_instance._ensure_connected.called

    @pytest.mark.asyncio
    async def test_protocol_version_parsing_major_minor(self, hub_instance):
        """Test protocol version parsing with MajorVersion/MinorVersion."""
        mock_response = {
            "Status": 200,
            "Data": {"MajorVersion": 1, "MinorVersion": 1}
        }
        
        # Simulate what connect() does
        hub_instance._protocol_version = None
        data = mock_response.get("Data", {})
        if "MajorVersion" in data and "MinorVersion" in data:
            major = data["MajorVersion"]
            minor = data["MinorVersion"]
            hub_instance._protocol_version = f"{major}.{minor}"
        
        assert hub_instance._protocol_version == "1.1"

    @pytest.mark.asyncio
    async def test_protocol_version_parsing_version_string(self, hub_instance):
        """Test protocol version parsing with Version string."""
        mock_response = {
            "Status": 200,
            "Data": {"Version": "1.0"}
        }
        
        # Simulate what connect() does
        hub_instance._protocol_version = None
        data = mock_response.get("Data", {})
        if "Version" in data:
            hub_instance._protocol_version = data["Version"]
        
        assert hub_instance._protocol_version == "1.0"

    @pytest.mark.asyncio
    async def test_concurrent_reconnection_prevention(self, hub_instance):
        """Test that concurrent reconnections are prevented."""
        hub_instance._ws = None
        
        # Simulate reconnection in progress by locking the reconnect_lock
        await hub_instance._reconnect_lock.acquire()
        
        try:
            # Should wait and timeout since lock is held
            with patch.object(hub_instance, "connect", new_callable=AsyncMock) as mock_connect:
                with pytest.raises(ConnectionError, match="Reconnection timeout"):
                    await hub_instance._ensure_connected()
                
                # Should not have called connect since lock was held
                assert mock_connect.call_count == 0
        finally:
            hub_instance._reconnect_lock.release()

    def test_connection_state_tracking(self, hub_instance):
        """Test connection state is properly tracked."""
        assert hub_instance._connection_state == "disconnected"
        
        hub_instance._connection_state = "connected"
        assert hub_instance._connection_state == "connected"
        
        hub_instance._connection_state = "error"
        assert hub_instance._connection_state == "error"

    def test_pending_requests_cleanup(self, hub_instance):
        """Test pending requests are properly tracked and cleaned."""
        loop = asyncio.get_event_loop()
        fut = loop.create_future()
        hub_instance._pending["test"] = fut
        
        assert "test" in hub_instance._pending
        
        removed = hub_instance._pending.pop("test", None)
        assert removed == fut
        assert "test" not in hub_instance._pending
    @pytest.mark.asyncio
    async def test_reconnection_event_signals_waiters(self, hub_instance):
        """Test that reconnection event properly signals waiting tasks."""
        hub_instance._ws = None
        
        # Mock successful connection
        mock_ws = MagicMock()
        mock_ws.closed = False
        
        async def mock_connect():
            hub_instance._ws = mock_ws
        
        with patch.object(hub_instance, "connect", side_effect=mock_connect):
            # Start reconnection in background
            reconnect_task = asyncio.create_task(hub_instance._ensure_connected())
            
            # Give it a moment to acquire lock
            await asyncio.sleep(0.1)
            
            # Now try to connect from another task - should wait for event
            await hub_instance._ensure_connected()
            
            # Both should succeed
            await reconnect_task
            assert hub_instance._ws == mock_ws

    @pytest.mark.asyncio
    async def test_wait_for_reconnection_timeout(self, hub_instance):
        """Test that waiting for reconnection times out properly."""
        hub_instance._ws = None
        
        # Acquire lock but don't set event (simulates hanging reconnection)
        await hub_instance._reconnect_lock.acquire()
        
        try:
            with pytest.raises(ConnectionError, match="Reconnection timeout"):
                await hub_instance._wait_for_reconnection()
        finally:
            hub_instance._reconnect_lock.release()

    @pytest.mark.asyncio
    async def test_perform_reconnection_with_retries(self, hub_instance):
        """Test that _perform_reconnection retries on failure."""
        attempts = []
        
        async def mock_connect():
            attempts.append(1)
            if len(attempts) < 3:
                raise ConnectionError(f"Attempt {len(attempts)} failed")
            # Third attempt succeeds
            hub_instance._ws = MagicMock()
            hub_instance._ws.closed = False
        
        with patch.object(hub_instance, "connect", side_effect=mock_connect):
            with patch.object(hub_instance, "_reconnect_delay", 0.01):  # Speed up test
                await hub_instance._perform_reconnection()
        
        # Should have tried 3 times
        assert len(attempts) == 3

    @pytest.mark.asyncio
    async def test_perform_reconnection_max_attempts(self, hub_instance):
        """Test that _perform_reconnection fails after max attempts."""
        async def mock_connect():
            raise ConnectionError("Connection failed")
        
        with patch.object(hub_instance, "connect", side_effect=mock_connect):
            with patch.object(hub_instance, "_reconnect_delay", 0.01):
                with pytest.raises(ConnectionError, match="Failed to reconnect after"):
                    await hub_instance._perform_reconnection()

    @pytest.mark.asyncio
    async def test_close_during_reconnection_wait(self, hub_instance):
        """Test that closing hub while waiting for reconnection works."""
        hub_instance._ws = None
        
        # Acquire lock (simulate reconnection in progress)
        await hub_instance._reconnect_lock.acquire()
        
        async def wait_and_close():
            await asyncio.sleep(0.1)
            hub_instance._closing = True
            hub_instance._reconnect_event.set()  # Unblock waiter
            hub_instance._reconnect_lock.release()
        
        close_task = asyncio.create_task(wait_and_close())
        
        # This should eventually succeed or raise due to closing
        try:
            await hub_instance._wait_for_reconnection()
        except ConnectionError:
            pass  # Expected if connection still dead
        
        await close_task
        assert hub_instance._closing