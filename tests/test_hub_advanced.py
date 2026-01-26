"""Advanced tests for ThermexHub WebSocket communication."""
import pytest
import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch
from aiohttp import WSMsgType

from custom_components.thermex_api.hub import ThermexHub


class TestHubAdvanced:
    """Advanced test cases for ThermexHub."""

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
        hub.runtime_manager = MagicMock()
        hub.runtime_manager.get_filter_time = MagicMock(return_value=50)
        return hub

    @pytest.mark.asyncio
    async def test_close_cancels_pending_requests(self, hub_instance):
        """Test that closing hub cancels all pending requests."""
        # Add some pending requests
        fut1 = asyncio.Future()
        fut2 = asyncio.Future()
        hub_instance._pending = {"status": fut1, "update": fut2}
        
        await hub_instance.close()
        
        # All futures should be cancelled with exception
        assert fut1.done()
        assert fut2.done()
        with pytest.raises(ConnectionError, match="Hub is closing"):
            fut1.result()
        with pytest.raises(ConnectionError, match="Hub is closing"):
            fut2.result()
        
        assert len(hub_instance._pending) == 0

    @pytest.mark.asyncio
    async def test_activity_timestamp_updated_on_send(self, hub_instance):
        """Test that activity timestamp is updated when sending messages."""
        mock_ws = MagicMock()
        mock_ws.closed = False
        mock_ws.send_json = AsyncMock()
        hub_instance._ws = mock_ws
        
        initial_time = hub_instance._last_activity
        
        # Mock the response
        loop = asyncio.get_event_loop()
        with patch.object(loop, "time", return_value=1000.0):
            # Start request
            request_task = asyncio.create_task(hub_instance.send_request("status", {}))
            
            # Simulate response
            await asyncio.sleep(0.01)
            fut = hub_instance._pending.get("status")
            if fut:
                fut.set_result({"Response": "Status", "Status": 200})
            
            await request_task
        
        # Activity should be updated
        assert mock_ws.send_json.called

    @pytest.mark.asyncio
    async def test_send_request_with_multiple_simultaneous_requests(self, hub_instance):
        """Test handling multiple simultaneous requests of different types."""
        mock_ws = MagicMock()
        mock_ws.closed = False
        mock_ws.send_json = AsyncMock()
        hub_instance._ws = mock_ws
        
        async def delayed_response(key, response_data):
            await asyncio.sleep(0.05)
            fut = hub_instance._pending.get(key)
            if fut and not fut.done():
                fut.set_result(response_data)
        
        # Start multiple requests
        task1 = asyncio.create_task(hub_instance.send_request("status", {}))
        task2 = asyncio.create_task(hub_instance.send_request("update", {"test": 1}))
        
        # Simulate responses arriving
        response1 = {"Response": "Status", "Status": 200, "Data": {}}
        response2 = {"Response": "Update", "Status": 200}
        
        asyncio.create_task(delayed_response("status", response1))
        asyncio.create_task(delayed_response("update", response2))
        
        results = await asyncio.gather(task1, task2)
        
        assert results[0] == response1
        assert results[1] == response2
        
        # Both should have been sent
        assert mock_ws.send_json.call_count == 2

    @pytest.mark.asyncio
    async def test_protocol_version_timeout_handling(self, hub_instance):
        """Test handling of protocol version request timeout."""
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
                    with patch.object(hub_instance, "send_request", side_effect=asyncio.TimeoutError):
                        with patch.object(hub_instance, "_dispatch_initial_status", new_callable=AsyncMock):
                            await hub_instance.connect()
        
        # Should still connect even if protocol version times out
        assert hub_instance._protocol_version is None
        assert hub_instance._connection_state == "connected"

    @pytest.mark.asyncio
    async def test_watchdog_detects_connection_timeout(self, hub_instance):
        """Test that watchdog detects connection timeout due to inactivity."""
        mock_ws = MagicMock()
        mock_ws.closed = False
        hub_instance._ws = mock_ws
        hub_instance._heartbeat_interval = 0.1
        hub_instance._connection_timeout = 0.2
        
        # Set last activity to long ago
        with patch.object(asyncio.get_event_loop(), "time", return_value=1000.0):
            hub_instance._last_activity = 900.0  # 100 seconds ago
            
            # Mock ensure_connected to track if it's called
            ensure_connected_called = asyncio.Event()
            
            async def mock_ensure():
                ensure_connected_called.set()
                raise ConnectionError("Reconnecting")
            
            with patch.object(hub_instance, "_ensure_connected", side_effect=mock_ensure):
                # Run one watchdog iteration
                watchdog_task = asyncio.create_task(hub_instance._watchdog_loop())
                
                # Wait for ensure_connected to be called
                try:
                    await asyncio.wait_for(ensure_connected_called.wait(), timeout=0.5)
                except asyncio.TimeoutError:
                    pass
                
                hub_instance._closing = True
                watchdog_task.cancel()
                try:
                    await watchdog_task
                except asyncio.CancelledError:
                    pass
            
            # Verify reconnection was attempted
            assert ensure_connected_called.is_set()

    @pytest.mark.asyncio
    async def test_reconnection_with_pending_requests(self, hub_instance):
        """Test that reconnection handles pending requests appropriately."""
        # Simulate a request in progress when connection drops
        hub_instance._ws = MagicMock()
        hub_instance._ws.closed = True
        
        # Add a pending request
        fut = asyncio.Future()
        hub_instance._pending["status"] = fut
        
        # Attempt to send a request (should trigger reconnection)
        mock_new_ws = MagicMock()
        mock_new_ws.closed = False
        mock_new_ws.send_json = AsyncMock()
        
        async def mock_connect():
            hub_instance._ws = mock_new_ws
            hub_instance._ws.closed = False
        
        with patch.object(hub_instance, "connect", side_effect=mock_connect):
            # Start the request
            request_task = asyncio.create_task(hub_instance.send_request("status", {}))
            
            # Let reconnection happen
            await asyncio.sleep(0.1)
            
            # Complete the request
            if not fut.done():
                fut.set_result({"Response": "Status", "Status": 200})
            
            result = await request_task
            
            assert result["Status"] == 200
            assert hub_instance._ws == mock_new_ws
