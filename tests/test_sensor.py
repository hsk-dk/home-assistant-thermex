"""Tests for sensor entities."""
import pytest
from datetime import datetime, timezone
from unittest.mock import MagicMock, AsyncMock, patch
from homeassistant.components.sensor import SensorDeviceClass

from custom_components.thermex_api.sensor import (
    ThermexRuntimeSensor,
    ThermexLastResetSensor,
    ThermexConnectionSensor,
    ThermexDelayedOffSensor,
    async_setup_entry,
)


class TestSensorSetup:
    """Test sensor setup."""

    @pytest.mark.asyncio
    async def test_async_setup_entry(self, mock_hass, mock_hub, mock_config_entry, mock_store):
        """Test sensor setup."""
        mock_hass.data = {
            "thermex_api": {
                mock_config_entry.entry_id: {
                    "hub": mock_hub,
                    "runtime_store": mock_store,
                }
            }
        }
        
        async_add_entities = AsyncMock()
        await async_setup_entry(mock_hass, mock_config_entry, async_add_entities)
        
        entities = async_add_entities.call_args[0][0]
        assert len(entities) == 4
        assert any(isinstance(e, ThermexRuntimeSensor) for e in entities)
        assert any(isinstance(e, ThermexLastResetSensor) for e in entities)
        assert any(isinstance(e, ThermexConnectionSensor) for e in entities)
        assert any(isinstance(e, ThermexDelayedOffSensor) for e in entities)


class TestRuntimeSensor:
    """Test ThermexRuntimeSensor entity."""

    @pytest.fixture
    def sensor_entity(self, mock_hub, mock_hass, mock_store):
        """Create a ThermexRuntimeSensor entity."""
        sensor = ThermexRuntimeSensor(mock_hub, mock_store)
        sensor.hass = mock_hass
        return sensor

    def test_sensor_initialization(self, sensor_entity, mock_hub):
        """Test sensor entity initialization."""
        assert sensor_entity._hub == mock_hub
        assert sensor_entity.device_class == SensorDeviceClass.DURATION

    def test_sensor_native_value_formatted(self, sensor_entity):
        """Test sensor formats runtime correctly."""
        sensor_entity._runtime_manager.get_total_seconds = MagicMock(return_value=3665)
        
        value = sensor_entity.native_value
        
        assert "1h" in value
        assert "1m" in value

    def test_sensor_extra_state_attributes(self, sensor_entity):
        """Test sensor includes total seconds in attributes."""
        sensor_entity._runtime_manager.get_total_seconds = MagicMock(return_value=3600)
        
        attrs = sensor_entity.extra_state_attributes
        
        assert attrs["total_seconds"] == 3600


class TestLastResetSensor:
    """Test ThermexLastResetSensor entity."""

    @pytest.fixture
    def sensor_entity(self, mock_hub, mock_hass, mock_store):
        """Create a ThermexLastResetSensor entity."""
        sensor = ThermexLastResetSensor(mock_hub, mock_store)
        sensor.hass = mock_hass
        return sensor

    def test_sensor_initialization(self, sensor_entity, mock_hub):
        """Test sensor entity initialization."""
        assert sensor_entity._hub == mock_hub
        assert sensor_entity.device_class == SensorDeviceClass.TIMESTAMP

    def test_sensor_native_value_no_reset(self, sensor_entity):
        """Test sensor value when no reset has occurred."""
        sensor_entity._runtime_manager.get_last_reset = MagicMock(return_value=None)
        
        assert sensor_entity.native_value is None

    def test_sensor_native_value_with_reset(self, sensor_entity):
        """Test sensor value with last reset time."""
        now = datetime.now(timezone.utc)
        sensor_entity._runtime_manager.get_last_reset = MagicMock(return_value=now)
        
        assert sensor_entity.native_value == now


class TestConnectionSensor:
    """Test ThermexConnectionSensor entity."""

    @pytest.fixture
    def sensor_entity(self, mock_hub, mock_hass):
        """Create a ThermexConnectionSensor entity."""
        sensor = ThermexConnectionSensor(mock_hub)
        sensor.hass = mock_hass
        return sensor

    def test_sensor_initialization(self, sensor_entity, mock_hub):
        """Test sensor entity initialization."""
        assert sensor_entity._hub == mock_hub
        assert "Connection" in sensor_entity.name

    def test_sensor_shows_connected(self, sensor_entity, mock_hub):
        """Test sensor shows connected state."""
        mock_hub.connected = True
        
        assert sensor_entity.native_value == "connected"

    def test_sensor_shows_disconnected(self, sensor_entity, mock_hub):
        """Test sensor shows disconnected state."""
        mock_hub.connected = False
        
        assert sensor_entity.native_value == "disconnected"


class TestDelayedOffSensor:
    """Test ThermexDelayedOffSensor entity."""

    @pytest.fixture
    def sensor_entity(self, mock_hub, mock_hass):
        """Create a ThermexDelayedOffSensor entity."""
        sensor = ThermexDelayedOffSensor(mock_hub)
        sensor.hass = mock_hass
        return sensor

    def test_sensor_initialization(self, sensor_entity, mock_hub):
        """Test sensor entity initialization."""
        assert sensor_entity._hub == mock_hub
        assert "Delayed Off" in sensor_entity.name

    def test_sensor_inactive_state(self, sensor_entity):
        """Test sensor shows inactive when no delayed off active."""
        sensor_entity._remaining_time = 0
        
        assert sensor_entity.native_value == "inactive"

    def test_sensor_active_state(self, sensor_entity):
        """Test sensor shows remaining time when active."""
        sensor_entity._remaining_time = 300
        
        value = sensor_entity.native_value
        assert "5:00" in value  # 5 minutes
