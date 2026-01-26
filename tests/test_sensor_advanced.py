"""Advanced tests for sensor entities."""
import pytest
from unittest.mock import MagicMock, AsyncMock, patch, call
from datetime import datetime, timedelta
from homeassistant.util import dt as dt_util

from custom_components.thermex_api.sensor import (
    RuntimeHoursSensor,
    LastResetSensor,
    ConnectionStatusSensor,
    DelayedTurnOffSensor,
)


class TestRuntimeHoursSensorAdvanced:
    """Advanced tests for RuntimeHoursSensor."""

    @pytest.fixture
    def runtime_sensor(self, mock_hub, mock_hass):
        """Create a RuntimeHoursSensor entity."""
        runtime_manager = MagicMock()
        runtime_manager.get_runtime_hours = MagicMock(return_value=42.5)
        
        sensor = RuntimeHoursSensor(mock_hub, runtime_manager, mock_hub.device_info)
        sensor.hass = mock_hass
        return sensor

    @pytest.mark.asyncio
    async def test_periodic_updates_only_when_fan_running(self, runtime_sensor):
        """Test that periodic updates only occur when fan is running."""
        with patch('custom_components.thermex_api.sensor.async_call_later') as mock_call_later:
            with patch.object(runtime_sensor, 'async_write_ha_state'):
                # Fan is off initially
                assert runtime_sensor._fan_is_running is False
                
                # Turn fan on
                runtime_sensor._handle_notify("fan", {
                    "Fan": {"fanonoff": 1, "fanspeed": 2}
                })
                
                # Should start periodic updates
                assert runtime_sensor._fan_is_running is True
                assert mock_call_later.called
                
                # Reset mock
                mock_call_later.reset_mock()
                
                # Turn fan off
                runtime_sensor._handle_notify("fan", {
                    "Fan": {"fanonoff": 0, "fanspeed": 0}
                })
                
                # Should stop periodic updates
                assert runtime_sensor._fan_is_running is False

    @pytest.mark.asyncio
    async def test_schedule_update_checks_fan_state(self, runtime_sensor):
        """Test that _schedule_update only schedules if fan is running."""
        with patch('custom_components.thermex_api.sensor.async_call_later') as mock_call_later:
            # Fan is off
            runtime_sensor._fan_is_running = False
            runtime_sensor._schedule_update()
            
            # Should not schedule
            assert not mock_call_later.called
            
            # Turn fan on
            runtime_sensor._fan_is_running = True
            runtime_sensor._schedule_update()
            
            # Should schedule
            assert mock_call_later.called

    @pytest.mark.asyncio
    async def test_ignores_non_fan_notifications(self, runtime_sensor):
        """Test that sensor ignores non-fan notifications."""
        with patch.object(runtime_sensor, 'async_write_ha_state') as mock_write:
            runtime_sensor._handle_notify("light", {"Light": {}})
            
            # Should not trigger state update
            assert not mock_write.called


class TestConnectionStatusSensorAdvanced:
    """Advanced tests for ConnectionStatusSensor."""

    @pytest.fixture
    def connection_sensor(self, mock_hub, mock_hass):
        """Create a ConnectionStatusSensor entity."""
        runtime_manager = MagicMock()
        
        sensor = ConnectionStatusSensor(mock_hub, runtime_manager, mock_hub.device_info)
        sensor.hass = mock_hass
        return sensor

    def test_sensor_value_includes_protocol_version(self, connection_sensor, mock_hub):
        """Test that sensor value includes protocol version when connected."""
        mock_hub._protocol_version = "1.1"
        mock_hub.get_coordinator_data.return_value = {
            "connection_state": "connected",
            "protocol_version": "1.1",
        }
        
        value = connection_sensor.native_value
        assert "connected" in value
        assert "v1.1" in value

    def test_sensor_attributes_include_diagnostics(self, connection_sensor, mock_hub):
        """Test that sensor attributes include diagnostic information."""
        mock_hub.get_coordinator_data.return_value = {
            "connection_state": "connected",
            "last_error": None,
            "watchdog_active": True,
            "time_since_activity": 5.2,
            "heartbeat_interval": 30,
            "connection_timeout": 120,
            "protocol_version": "1.1",
        }
        mock_hub.protocol_version = "1.1"
        
        attrs = connection_sensor.extra_state_attributes
        
        assert attrs["watchdog_active"] is True
        assert attrs["time_since_activity"] == 5.2
        assert attrs["heartbeat_interval"] == 30
        assert attrs["connection_timeout"] == 120
        assert attrs["protocol_version"] == "1.1"

    @pytest.mark.asyncio
    async def test_updates_on_any_notification(self, connection_sensor):
        """Test that connection sensor updates on any notification."""
        with patch.object(connection_sensor, 'async_write_ha_state') as mock_write:
            # Test various notification types
            connection_sensor._handle_notify("fan", {})
            connection_sensor._handle_notify("light", {})
            connection_sensor._handle_notify("decolight", {})
            
            # Should update on all
            assert mock_write.call_count == 3


class TestLastResetSensorAdvanced:
    """Advanced tests for LastResetSensor."""

    @pytest.fixture
    def last_reset_sensor(self, mock_hub, mock_hass):
        """Create a LastResetSensor entity."""
        runtime_manager = MagicMock()
        
        sensor = LastResetSensor(mock_hub, runtime_manager, mock_hub.device_info)
        sensor.hass = mock_hass
        return sensor

    def test_sensor_handles_invalid_iso_format(self, last_reset_sensor):
        """Test sensor handles invalid ISO format gracefully."""
        # Return invalid ISO format
        last_reset_sensor._runtime_manager.get_last_reset.return_value = "invalid-date"
        
        with patch('custom_components.thermex_api.sensor.parse_datetime', return_value=None):
            value = last_reset_sensor.native_value
            
            # Should return None for invalid date
            assert value is None

    def test_sensor_returns_datetime_object(self, last_reset_sensor):
        """Test sensor returns proper datetime object."""
        iso_time = "2026-01-15T10:30:00+00:00"
        last_reset_sensor._runtime_manager.get_last_reset.return_value = iso_time
        
        with patch('custom_components.thermex_api.sensor.parse_datetime') as mock_parse:
            expected_dt = datetime(2026, 1, 15, 10, 30, 0)
            mock_parse.return_value = expected_dt
            
            value = last_reset_sensor.native_value
            
            assert value == expected_dt
            mock_parse.assert_called_once_with(iso_time)


class TestDelayedTurnOffSensorAdvanced:
    """Advanced tests for DelayedTurnOffSensor."""

    @pytest.fixture
    def delayed_sensor(self, mock_hub, mock_hass):
        """Create a DelayedTurnOffSensor entity."""
        runtime_manager = MagicMock()
        
        sensor = DelayedTurnOffSensor(mock_hub, runtime_manager, mock_hub.device_info, "test_entry_id")
        sensor.hass = mock_hass
        return sensor

    def test_sensor_calculates_scheduled_time(self, delayed_sensor, mock_hass):
        """Test sensor calculates scheduled time from fan attributes."""
        from datetime import datetime, timedelta
        
        scheduled_time = datetime.now() + timedelta(minutes=10)
        fan_state = MagicMock()
        fan_state.attributes = {
            "delayed_off_active": True,
            "delayed_off_scheduled_time": scheduled_time.isoformat(),
        }
        mock_hass.states.get = MagicMock(return_value=fan_state)
        mock_hass.data = {"thermex_api": {"test_entry_id": {"hub": delayed_sensor._hub}}}
        
        with patch('custom_components.thermex_api.sensor.dt_util.parse_datetime', return_value=scheduled_time):
            value = delayed_sensor.native_value
            
            # Should return the scheduled time
            assert value is not None

    def test_sensor_returns_none_when_delayed_off_inactive(self, delayed_sensor, mock_hass):
        """Test sensor returns None when delayed turn-off is not active."""
        fan_state = MagicMock()
        fan_state.attributes = {
            "delayed_off_active": False,
            "delayed_off_scheduled_time": None,
        }
        mock_hass.states.get = MagicMock(return_value=fan_state)
        mock_hass.data = {"thermex_api": {"test_entry_id": {"hub": delayed_sensor._hub}}}
        
        value = delayed_sensor.native_value
        
        assert value is None

    @pytest.mark.asyncio
    async def test_sensor_subscribes_to_delayed_off_notifications(self, delayed_sensor, mock_hass):
        """Test sensor properly subscribes to delayed turn-off notifications."""
        with patch('custom_components.thermex_api.sensor.async_dispatcher_connect') as mock_connect:
            delayed_sensor._unsub = MagicMock()
            
            await delayed_sensor.async_added_to_hass()
            
            # Should subscribe to notifications
            assert mock_connect.called
