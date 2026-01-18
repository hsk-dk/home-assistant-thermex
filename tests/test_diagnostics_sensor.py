"""Tests for diagnostics sensor."""
import pytest
from unittest.mock import MagicMock

from custom_components.thermex_api.diagnostics_sensor import ThermexDiagnosticsSensor


class TestThermexDiagnosticsSensor:
    """Test ThermexDiagnosticsSensor."""

    @pytest.fixture
    def mock_coordinator(self):
        """Create a mock coordinator."""
        coordinator = MagicMock()
        coordinator.api = MagicMock()
        coordinator.api.is_connected = True
        coordinator.api.last_error = None
        coordinator.last_update_success = True
        coordinator.async_request_refresh = MagicMock()
        return coordinator

    @pytest.fixture
    def sensor(self, mock_coordinator):
        """Create a ThermexDiagnosticsSensor instance."""
        return ThermexDiagnosticsSensor(mock_coordinator)

    def test_sensor_initialization(self, sensor):
        """Test sensor initialization."""
        assert sensor._attr_name == "Thermex Diagnostics"
        assert sensor._attr_unique_id == "thermex_diagnostics"

    def test_sensor_state_connected(self, sensor, mock_coordinator):
        """Test sensor state when connected."""
        mock_coordinator.api.is_connected = True
        assert sensor.state == "connected"

    def test_sensor_state_disconnected(self, sensor, mock_coordinator):
        """Test sensor state when disconnected."""
        mock_coordinator.api.is_connected = False
        assert sensor.state == "disconnected"

    def test_sensor_extra_state_attributes(self, sensor, mock_coordinator):
        """Test sensor extra state attributes."""
        mock_coordinator.api.last_error = "Test error"
        mock_coordinator.last_update_success = False
        
        attrs = sensor.extra_state_attributes
        
        assert attrs["last_error"] == "Test error"
        assert attrs["last_update"] is False

    @pytest.mark.asyncio
    async def test_sensor_async_update(self, sensor, mock_coordinator):
        """Test sensor async update."""
        await sensor.async_update()
        mock_coordinator.async_request_refresh.assert_called_once()
