"""Tests for hub module."""
import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock
import aiohttp
from aiohttp import WSMsgType

from custom_components.thermex_api.hub import ThermexHub


class TestThermexHub:
    """Test ThermexHub class."""

    @pytest.fixture
    def hub(self, mock_hass):
        """Create a ThermexHub instance."""
        return ThermexHub(mock_hass, "192.168.1.100", "test_api_key", "test_entry_id")

    def test_hub_initialization(self, hub):
        """Test hub initialization."""
        assert hub._host == "192.168.1.100"
        assert hub._api_key == "test_api_key"
        assert hub.unique_id == "thermex_192_168_1_100"
        assert hub._connection_state == "disconnected"
        assert hub._ws is None
        assert hub._session is None

    def test_hub_device_info(self, hub):
        """Test hub device info property."""
        device_info = hub.device_info
        assert device_info["identifiers"] == {("thermex_api", hub.unique_id)}
        assert device_info["name"] == "Thermex Hood"
        assert device_info["manufacturer"] == "Thermex"

    def test_hub_protocol_version(self, hub):
        """Test protocol version property."""
        assert hub.protocol_version is None
        hub._protocol_version = "1.5"
        assert hub.protocol_version == "1.5"

    def test_hub_startup_complete(self, hub):
        """Test startup_complete property."""
        assert hub.startup_complete is False
        hub._startup_complete = True
        assert hub.startup_complete is True

    def test_configure_watchdog(self, hub):
        """Test watchdog configuration."""
        hub.configure_watchdog(heartbeat_interval=45, connection_timeout=180)
        assert hub._heartbeat_interval == 45
        assert hub._connection_timeout == 180

    @pytest.mark.asyncio
    async def test_connect_success(self, hub):
        """Test successful connection."""
        mock_session = MagicMock()
        mock_ws = AsyncMock()
        mock_ws.closed = False
        mock_ws.send_str = AsyncMock()
        mock_ws.receive = AsyncMock(return_value=MagicMock(
            type=WSMsgType.TEXT,
            data='{"Response":"Authenticate","Success":true}'
        ))
        mock_session.ws_connect = AsyncMock(return_value=mock_ws)
        
        with patch('aiohttp.ClientSession', return_value=mock_session):
            result = await hub.connect()
            assert result is True
            assert hub._ws == mock_ws
            assert hub._connection_state == "connected"

    @pytest.mark.asyncio
    async def test_connect_authentication_failure(self, hub):
        """Test connection with authentication failure."""
        mock_session = MagicMock()
        mock_ws = AsyncMock()
        mock_ws.closed = False
        mock_ws.send_str = AsyncMock()
        mock_ws.receive = AsyncMock(return_value=MagicMock(
            type=WSMsgType.TEXT,
            data='{"Response":"Authenticate","Success":false}'
        ))
        mock_ws.close = AsyncMock()
        mock_session.ws_connect = AsyncMock(return_value=mock_ws)
        
        with patch('aiohttp.ClientSession', return_value=mock_session):
            result = await hub.connect()
            assert result is False
            assert hub._connection_state == "disconnected"

    @pytest.mark.asyncio
    async def test_connect_with_exception(self, hub):
        """Test connection handling exceptions."""
        with patch('aiohttp.ClientSession') as mock_session_class:
            mock_session_class.side_effect = Exception("Connection error")
            result = await hub.connect()
            assert result is False
            assert "Connection error" in str(hub.last_error)

    @pytest.mark.asyncio
    async def test_disconnect(self, hub):
        """Test disconnection."""
        mock_ws = AsyncMock()
        mock_ws.closed = False
        mock_ws.close = AsyncMock()
        hub._ws = mock_ws
        hub._connection_state = "connected"
        
        await hub.disconnect()
        
        mock_ws.close.assert_called_once()
        assert hub._closing is True

    @pytest.mark.asyncio
    async def test_send_request_success(self, hub):
        """Test sending request successfully."""
        mock_ws = AsyncMock()
        mock_ws.closed = False
        mock_ws.send_str = AsyncMock()
        hub._ws = mock_ws
        hub._connection_state = "connected"
        
        # Create a future that will be resolved
        future = asyncio.Future()
        future.set_result({"Response": "Status", "Success": True})
        
        with patch.object(hub, '_generate_request_id', return_value="req_123"):
            # Manually set the future in pending
            hub._pending["req_123"] = future
            
            result = await hub.send_request("Status", {})
            assert result == {"Response": "Status", "Success": True}

    @pytest.mark.asyncio
    async def test_send_request_timeout(self, hub):
        """Test request timeout."""
        mock_ws = AsyncMock()
        mock_ws.closed = False
        mock_ws.send_str = AsyncMock()
        hub._ws = mock_ws
        hub._connection_state = "connected"
        
        with patch.object(hub, '_generate_request_id', return_value="req_timeout"):
            with pytest.raises(asyncio.TimeoutError):
                await hub.send_request("Status", {}, timeout=0.1)

    @pytest.mark.asyncio
    async def test_request_fallback_status(self, hub):
        """Test fallback status request."""
        hub.send_request = AsyncMock(return_value={
            "Light": {"lightonoff": 1, "lightbrightness": 200},
            "Fan": {"fanspeed": 2}
        })
        
        result = await hub.request_fallback_status("test_entity")
        assert result["Light"]["lightonoff"] == 1
        assert result["Fan"]["fanspeed"] == 2

    def test_get_coordinator_data(self, hub):
        """Test getting coordinator data."""
        hub._connection_state = "connected"
        hub.last_error = None
        hub._heartbeat_interval = 30
        
        data = hub.get_coordinator_data()
        assert data["connection_state"] == "connected"
        assert data["last_error"] is None
        assert data["heartbeat_interval"] == 30

    @pytest.mark.asyncio
    async def test_receive_message_status_response(self, hub, mock_hass):
        """Test receiving status response message."""
        hub._hass = mock_hass
        
        message = {
            "Response": "Status",
            "RequestId": "req_123",
            "Light": {"lightonoff": 1},
            "Fan": {"fanspeed": 2}
        }
        
        future = asyncio.Future()
        hub._pending["req_123"] = future
        
        with patch('custom_components.thermex_api.hub.async_dispatcher_send') as mock_dispatch:
            hub._receive_message(message)
            
            # Check future was resolved
            assert future.done()
            assert future.result() == message
            
            # Check dispatchers were called
            assert mock_dispatch.call_count >= 2

    @pytest.mark.asyncio
    async def test_receive_message_notify(self, hub, mock_hass):
        """Test receiving notify message."""
        hub._hass = mock_hass
        
        message = {
            "Notify": "Light",
            "Light": {"lightonoff": 1, "lightbrightness": 150}
        }
        
        with patch('custom_components.thermex_api.hub.async_dispatcher_send') as mock_dispatch:
            hub._receive_message(message)
            
            mock_dispatch.assert_called()
            call_args = mock_dispatch.call_args[0]
            assert call_args[1] == "thermex_api_notify"
            assert call_args[2] == "light"

    @pytest.mark.asyncio
    async def test_ensure_connected_already_connected(self, hub):
        """Test ensure_connected when already connected."""
        mock_ws = MagicMock()
        mock_ws.closed = False
        hub._ws = mock_ws
        
        # Should not raise
        await hub._ensure_connected()

    @pytest.mark.asyncio
    async def test_ensure_connected_while_closing(self, hub):
        """Test ensure_connected raises when closing."""
        hub._closing = True
        
        with pytest.raises(ConnectionError, match="Hub is closing"):
            await hub._ensure_connected()

    def test_generate_request_id(self, hub):
        """Test request ID generation."""
        req_id = hub._generate_request_id()
        assert req_id.startswith("req_")
        assert len(req_id) > 4

    @pytest.mark.asyncio
    async def test_close_hub(self, hub):
        """Test closing the hub."""
        mock_ws = AsyncMock()
        mock_ws.closed = False
        mock_ws.close = AsyncMock()
        hub._ws = mock_ws
        
        mock_recv_task = MagicMock()
        mock_recv_task.cancel = MagicMock()
        hub._recv_task = mock_recv_task
        
        await hub.disconnect()
        
        assert hub._closing is True
        mock_ws.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_handle_connection_lost(self, hub):
        """Test handling connection loss."""
        hub._connection_state = "connected"
        
        await hub._handle_connection_lost()
        
        assert hub._connection_state == "disconnected"

    @pytest.mark.asyncio
    async def test_reconnect_with_backoff(self, hub):
        """Test reconnection with backoff."""
        hub.connect = AsyncMock(side_effect=[False, False, True])
        
        with patch('asyncio.sleep', new_callable=AsyncMock):
            result = await hub._reconnect_with_backoff()
            assert result is True
            assert hub.connect.call_count == 3
