"""Tests for sensor entities."""
import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from datetime import datetime, timedelta

from custom_components.thermex_api.sensor import (
    RuntimeHoursSensor,
    LastResetSensor,
    ConnectionStatusSensor,
    DelayedTurnOffSensor,
    async_setup_entry,
)


class TestSensorSetup:
    """Test sensor setup."""

    @pytest.mark.asyncio
    async def test_async_setup_entry(self, mock_hass, mock_hub, mock_config_entry):
        """Test sensor setup from config entry."""
        runtime_manager = MagicMock()
        mock_hass.data = {
            "thermex_api": {
                mock_config_entry.entry_id: {
                    "hub": mock_hub,
                    "runtime_manager": runtime_manager,
                }
            }
        }
        
        async_add_entities = AsyncMock()
        
        await async_setup_entry(mock_hass, mock_config_entry, async_add_entities)
        
        async_add_entities.assert_called_once()
        entities = async_add_entities.call_args[0][0]
        assert len(entities) == 4
        assert isinstance(entities[0], LastResetSensor)
        assert isinstance(entities[1], RuntimeHoursSensor)
        assert isinstance(entities[2], ConnectionStatusSensor)
        assert isinstance(entities[3], DelayedTurnOffSensor)


class TestRuntimeHoursSensor:
    """Test RuntimeHoursSensor entity."""

    @pytest.fixture
    def runtime_sensor(self, mock_hub, mock_hass):
        """Create a RuntimeHoursSensor entity."""
        runtime_manager = MagicMock()
        runtime_manager.get_runtime_hours = MagicMock(return_value=42.5)
        
        sensor = RuntimeHoursSensor(mock_hub, runtime_manager, mock_hub.device_info)
        sensor.hass = mock_hass
        return sensor

    def test_sensor_initialization(self, runtime_sensor, mock_hub):
        """Test sensor entity initialization."""
        assert runtime_sensor._hub == mock_hub
        assert runtime_sensor.unit_of_measurement == "h"

    def test_sensor_state(self, runtime_sensor):
        """Test sensor returns correct native value."""
        assert runtime_sensor.native_value == 42.5

    @pytest.mark.asyncio
    async def test_sensor_handles_notify(self, runtime_sensor, mock_hass):
        """Test sensor updates on fan notifications."""
        runtime_sensor._runtime_manager.get_runtime_hours.return_value = 50.0
        
        runtime_sensor._handle_notify("fan", {"Fan": {"fanspeed": 2}})
        
        # State should be updated
        assert runtime_sensor.native_value == 50.0


class TestLastResetSensor:
    """Test LastResetSensor entity."""

    @pytest.fixture
    def reset_sensor(self, mock_hub, mock_hass):
        """Create a LastResetSensor entity."""
        runtime_manager = MagicMock()
        reset_time = datetime(2026, 1, 1, 12, 0, 0)
        runtime_manager.get_last_reset = MagicMock(return_value=reset_time)
        
        sensor = LastResetSensor(mock_hub, runtime_manager, mock_hub.device_info)
        sensor.hass = mock_hass
        return sensor

    def test_sensor_initialization(self, reset_sensor, mock_hub):
        """Test sensor entity initialization."""
        assert reset_sensor._hub == mock_hub

    def test_sensor_state_with_reset_time(self, reset_sensor):
        """Test sensor returns reset datetime."""
        # Return ISO string and expect parsed datetime
        reset_sensor._runtime_manager.get_last_reset.return_value = "2026-01-01T12:00:00"
        result = reset_sensor.native_value
        assert result is not None
        assert result.year == 2026
        assert result.month == 1
        assert result.day == 1

    def test_sensor_state_with_no_reset(self, reset_sensor):
        """Test sensor returns None when no reset recorded."""
        reset_sensor._runtime_manager.get_last_reset.return_value = None
        assert reset_sensor.native_value is None


class TestConnectionStatusSensor:
    """Test ConnectionStatusSensor entity."""

    @pytest.fixture
    def status_sensor(self, mock_hub, mock_hass):
        """Create a ConnectionStatusSensor entity."""
        runtime_manager = MagicMock()
        
        sensor = ConnectionStatusSensor(mock_hub, runtime_manager, mock_hub.device_info)
        sensor.hass = mock_hass
        return sensor

    def test_sensor_initialization(self, status_sensor, mock_hub):
        """Test sensor entity initialization."""
        assert status_sensor._hub == mock_hub

    def test_sensor_state_connected(self, status_sensor):
        """Test sensor returns connected state with protocol version."""
        status_sensor._hub.get_coordinator_data = MagicMock(return_value={"connection_state": "connected"})
        status_sensor._hub.protocol_version = "1.0"
        assert status_sensor.native_value == "connected (v1.0)"

    def test_sensor_state_disconnected(self, status_sensor):
        """Test sensor returns disconnected state."""
        status_sensor._hub.get_coordinator_data = MagicMock(return_value={"connection_state": "disconnected"})
        status_sensor._hub.protocol_version = None
        assert status_sensor.native_value == "disconnected"

    def test_sensor_extra_attributes(self, status_sensor):
        """Test sensor returns diagnostic attributes."""
        status_sensor._hub.get_coordinator_data = MagicMock(return_value={
            "last_error": None,
            "watchdog_active": True,
            "time_since_activity": 10,
            "heartbeat_interval": 30,
            "connection_timeout": 120,
        })
        
        attrs = status_sensor.extra_state_attributes
        assert attrs["watchdog_active"] is True
        assert attrs["time_since_activity"] == 10


class TestDelayedTurnOffSensor:
    """Test DelayedTurnOffSensor entity."""

    @pytest.fixture
    def delayed_sensor(self, mock_hub, mock_hass):
        """Create a DelayedTurnOffSensor entity."""
        runtime_manager = MagicMock()
        
        sensor = DelayedTurnOffSensor(
            mock_hub,
            runtime_manager,
            mock_hub.device_info,
            "test_entry_id"
        )
        sensor.hass = mock_hass
        return sensor

    def test_sensor_initialization(self, delayed_sensor, mock_hub):
        """Test sensor entity initialization."""
        assert delayed_sensor._hub == mock_hub
        assert delayed_sensor._entry_id == "test_entry_id"

    def test_sensor_state_not_active(self, delayed_sensor, mock_hass):
        """Test sensor state when delayed off is not active."""
        mock_hass.data = {
            "thermex_api": {
                "test_entry_id": {
                    "fan": MagicMock(_delayed_off_active=False)
                }
            }
        }
        
        assert delayed_sensor.native_value == "off"

    def test_sensor_state_active_with_time(self, delayed_sensor, mock_hass):
        """Test sensor state when delayed off is active."""
        mock_hass.data = {
            "thermex_api": {
                "test_entry_id": {
                    "fan": MagicMock(
                        _delayed_off_active=True,
                        _delayed_off_remaining=300
                    )
                }
            }
        }
        
        assert delayed_sensor.native_value == 300

    def test_sensor_state_no_fan(self, delayed_sensor, mock_hass):
        """Test sensor state when fan entity doesn't exist."""
        mock_hass.data = {"thermex_api": {}}
        
        assert delayed_sensor.native_value == "off"

    def test_sensor_extra_attributes(self, delayed_sensor, mock_hass):
        """Test sensor extra state attributes."""
        mock_hass.data = {
            "thermex_api": {
                "test_entry_id": {
                    "fan": MagicMock(
                        _delayed_off_active=True,
                        _delayed_off_remaining=180
                    )
                }
            }
        }
        
        attrs = delayed_sensor.extra_state_attributes
        
        assert "active" in attrs
        assert "remaining_seconds" in attrs
        assert attrs["active"] is True
        assert attrs["remaining_seconds"] == 180
