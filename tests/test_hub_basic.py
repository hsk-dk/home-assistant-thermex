"""Tests for ThermexHub basic functionality."""
import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from custom_components.thermex_api.hub import ThermexHub
from homeassistant.helpers.entity import DeviceInfo


class TestThermexHubBasic:
    """Test basic ThermexHub functionality."""

    @pytest.fixture
    def mock_session(self):
        """Create a mock session."""
        session = MagicMock()
        session.ws_connect = AsyncMock()
        return session

    @pytest.fixture
    def hub(self, mock_session):
        """Create a ThermexHub instance."""
        return ThermexHub(
            session=mock_session,
            host="192.168.1.100",
            serial_number="TEST123",
            mac_address="AA:BB:CC:DD:EE:FF"
        )

    def test_hub_initialization(self, hub):
        """Test hub initializes with correct properties."""
        assert hub.host == "192.168.1.100"
        assert hub.serial_number == "TEST123"
        assert hub.mac_address == "AA:BB:CC:DD:EE:FF"
        assert hub._closing is False
        assert hub._reconnecting is False

    def test_hub_unique_id(self, hub):
        """Test hub generates correct unique_id."""
        # unique_id should be serial number
        assert "TEST123" in str(hub)

    def test_hub_device_info(self, hub):
        """Test hub provides correct device info."""
        device_info = hub.device_info
        
        assert isinstance(device_info, DeviceInfo)
        assert device_info["identifiers"] == {("thermex_api", "TEST123")}
        assert device_info["name"] == "Thermex TEST123"
        assert device_info["manufacturer"] == "Thermex"
        assert device_info["connections"] == {("mac", "AA:BB:CC:DD:EE:FF")}

    def test_hub_configure_watchdog(self, hub):
        """Test watchdog configuration."""
        hub.configure_watchdog(heartbeat_interval=60, connection_timeout=180)
        
        assert hub._heartbeat_interval == 60
        assert hub._connection_timeout == 180

    def test_hub_startup_complete_property(self, hub):
        """Test startup_complete property."""
        assert hub.startup_complete is False
        
        hub._startup_complete = True
        assert hub.startup_complete is True

    def test_hub_is_connected(self, hub):
        """Test is_connected property."""
        # No websocket connection
        assert hub._ws is None
        
        # Mock connected websocket
        mock_ws = MagicMock()
        mock_ws.closed = False
        hub._ws = mock_ws
        # is_connected checks if ws exists and is not closed
        assert hub._ws is not None
        assert not hub._ws.closed

    def test_hub_closing_flag(self, hub):
        """Test closing flag."""
        assert hub._closing is False
        
        hub._closing = True
        assert hub._closing is True

    @pytest.mark.asyncio
    async def test_hub_close(self, hub):
        """Test hub close method."""
        mock_ws = MagicMock()
        mock_ws.close = AsyncMock()
        mock_ws.closed = False
        hub._ws = mock_ws
        
        # Mock the _stop_watchdog method
        hub._stop_watchdog = MagicMock()
        
        await hub.close()
        
        assert hub._closing is True
        mock_ws.close.assert_called_once()
        hub._stop_watchdog.assert_called_once()
