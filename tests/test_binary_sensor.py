"""Tests for binary sensor entities."""
import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from homeassistant.components.binary_sensor import BinarySensorDeviceClass

from custom_components.thermex_api.binary_sensor import ThermexFilterAlertSensor, async_setup_entry


class TestBinarySensorSetup:
    """Test binary sensor setup."""

    @pytest.mark.asyncio
    async def test_async_setup_entry(self, mock_hass, mock_hub, mock_config_entry):
        """Test binary sensor setup."""
        mock_hass.data = {
            "thermex_api": {
                mock_config_entry.entry_id: {
                    "hub": mock_hub,
                }
            }
        }
        
        async_add_entities = AsyncMock()
        await async_setup_entry(mock_hass, mock_config_entry, async_add_entities)
        
        entities = async_add_entities.call_args[0][0]
        assert len(entities) == 1
        assert isinstance(entities[0], ThermexFilterAlertSensor)


class TestFilterAlertSensor:
    """Test ThermexFilterAlertSensor entity."""

    @pytest.fixture
    def sensor_entity(self, mock_hub, mock_hass):
        """Create a ThermexFilterAlertSensor entity."""
        sensor = ThermexFilterAlertSensor(mock_hub)
        sensor.hass = mock_hass
        return sensor

    def test_sensor_initialization(self, sensor_entity, mock_hub):
        """Test sensor entity initialization."""
        assert sensor_entity._hub == mock_hub
        assert sensor_entity._is_on is False
        assert sensor_entity.device_class == BinarySensorDeviceClass.PROBLEM

    def test_sensor_handle_notify_filter_on(self, sensor_entity):
        """Test sensor updates when filter alert is on."""
        with patch.object(sensor_entity, 'async_write_ha_state'):
            sensor_entity._handle_notify("filteralert", {
                "Filteralert": {"filteralert": 1}
            })
            
            assert sensor_entity.is_on is True

    def test_sensor_handle_notify_filter_off(self, sensor_entity):
        """Test sensor updates when filter alert is off."""
        sensor_entity._is_on = True
        
        with patch.object(sensor_entity, 'async_write_ha_state'):
            sensor_entity._handle_notify("filteralert", {
                "Filteralert": {"filteralert": 0}
            })
            
            assert sensor_entity.is_on is False

    def test_sensor_ignores_wrong_notifications(self, sensor_entity):
        """Test sensor ignores non-filteralert notifications."""
        original_state = sensor_entity._is_on
        
        with patch.object(sensor_entity, 'async_write_ha_state'):
            sensor_entity._handle_notify("fan", {"Fan": {"fanonoff": 1}})
        
        assert sensor_entity._is_on == original_state

    def test_sensor_unique_id(self, sensor_entity, mock_hub):
        """Test sensor unique ID."""
        assert sensor_entity.unique_id == f"{mock_hub.device_id}_filter_alert"

    def test_sensor_name(self, sensor_entity):
        """Test sensor name."""
        assert "Filter Alert" in sensor_entity.name
