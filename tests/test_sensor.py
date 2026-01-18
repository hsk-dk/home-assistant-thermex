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
        # Don't check unit_of_measurement before entity is added to platform

    def test_sensor_state(self, runtime_sensor):
        """Test sensor returns correct native value."""
        assert runtime_sensor.native_value == 42.5

    @pytest.mark.asyncio
    async def test_sensor_handles_notify(self, runtime_sensor):
        """Test sensor updates on fan notifications."""
        runtime_sensor._runtime_manager.get_runtime_hours.return_value = 50.0
        
        # Mock async_write_ha_state to avoid platform requirements
        with patch.object(runtime_sensor, 'async_write_ha_state'):
            runtime_sensor._handle_notify("fan", {"Fan": {"fanspeed": 2}})
        
        # Verify the value would be updated
        assert runtime_sensor.native_value == 50.0

    @pytest.mark.asyncio
    async def test_sensor_async_will_remove_from_hass(self, runtime_sensor):
        """Test sensor cleanup cancels timer."""
        # Setup mock timer
        mock_timer = MagicMock()
        runtime_sensor._update_timer = mock_timer
        runtime_sensor._unsub = MagicMock()
        
        await runtime_sensor.async_will_remove_from_hass()
        
        # Should cancel timer
        mock_timer.assert_called_once()


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
        fan_state = MagicMock()
        fan_state.attributes = {
            "delayed_off_active": False,
            "delayed_off_scheduled_time": None,
        }
        mock_hass.states.get = MagicMock(return_value=fan_state)
        mock_hass.data = {
            "thermex_api": {
                "test_entry_id": {
                    "hub": delayed_sensor._hub
                }
            }
        }
        
        # When no scheduled time, should return None
        assert delayed_sensor.native_value is None

    def test_sensor_state_active_with_time(self, delayed_sensor, mock_hass):
        """Test sensor state when delayed off is active."""
        from datetime import datetime
        scheduled_time = "2026-01-18T12:00:00"
        
        fan_state = MagicMock()
        fan_state.attributes = {
            "delayed_off_active": True,
            "delayed_off_scheduled_time": scheduled_time,
            "delayed_off_remaining": 300
        }
        mock_hass.states.get = MagicMock(return_value=fan_state)
        mock_hass.data = {
            "thermex_api": {
                "test_entry_id": {
                    "hub": delayed_sensor._hub
                }
            }
        }
        
        # Should return parsed datetime
        result = delayed_sensor.native_value
        assert result is not None
        assert result.year == 2026

    def test_sensor_state_no_fan(self, delayed_sensor, mock_hass):
        """Test sensor state when fan entity doesn't exist."""
        mock_hass.states.get = MagicMock(return_value=None)
        mock_hass.data = {"thermex_api": {}}
        
        assert delayed_sensor.native_value is None

    def test_sensor_extra_attributes(self, delayed_sensor, mock_hass):
        """Test sensor extra state attributes."""
        fan_state = MagicMock()
        fan_state.attributes = {
            "delayed_off_active": True,
            "delayed_off_remaining": 180,
            "delayed_off_delay": 10,
        }
        mock_hass.states.get = MagicMock(return_value=fan_state)
        mock_hass.data = {
            "thermex_api": {
                "test_entry_id": {
                    "hub": delayed_sensor._hub
                }
            }
        }
        
        attrs = delayed_sensor.extra_state_attributes
        
        assert "delayed_off_active" in attrs
        assert "delayed_off_remaining" in attrs
        assert attrs["delayed_off_active"] is True
        assert attrs["delayed_off_remaining"] == 180

    def test_sensor_handle_delayed_off_notify(self, delayed_sensor):
        """Test sensor handles delayed_turn_off notifications."""
        with patch.object(delayed_sensor, 'async_write_ha_state') as mock_write:
            delayed_sensor._handle_delayed_off_notify("delayed_turn_off", {})
            
            # Should trigger state write
            mock_write.assert_called_once()

    def test_sensor_handle_fan_notify(self, delayed_sensor):
        """Test sensor handles fan notifications."""
        with patch.object(delayed_sensor, 'async_write_ha_state') as mock_write:
            delayed_sensor._handle_delayed_off_notify("fan", {})
            
            # Should trigger state write
            mock_write.assert_called_once()
