"""Tests for binary sensor entities."""
import pytest
from unittest.mock import MagicMock, AsyncMock

from custom_components.thermex_api.binary_sensor import (
    ThermexFilterAlert,
    async_setup_entry,
)


class TestBinarySensorSetup:
    """Test binary sensor setup."""

    @pytest.mark.asyncio
    async def test_async_setup_entry(self, mock_hass, mock_hub, mock_config_entry):
        """Test binary sensor setup from config entry."""
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
        assert len(entities) == 1
        assert isinstance(entities[0], ThermexFilterAlert)


class TestThermexFilterAlert:
    """Test ThermexFilterAlert binary sensor."""

    @pytest.fixture
    def filter_alert(self, mock_hub, mock_hass):
        """Create a ThermexFilterAlert entity."""
        runtime_manager = MagicMock()
        runtime_manager.get_runtime_hours = MagicMock(return_value=10.0)
        runtime_manager.get_days_since_reset = MagicMock(return_value=5)
        
        options = {
            "fan_alert_hours": 30,
            "fan_alert_days": 90,
        }
        
        sensor = ThermexFilterAlert(
            mock_hub,
            runtime_manager,
            options,
            mock_hub.device_info
        )
        sensor.hass = mock_hass
        return sensor

    def test_sensor_initialization(self, filter_alert, mock_hub):
        """Test sensor entity initialization."""
        assert filter_alert._hub == mock_hub
        assert filter_alert._options["fan_alert_hours"] == 30
        assert filter_alert._options["fan_alert_days"] == 90

    def test_sensor_not_triggered_below_thresholds(self, filter_alert):
        """Test sensor is off when below both thresholds."""
        filter_alert._runtime_manager.get_runtime_hours.return_value = 10.0
        filter_alert._runtime_manager.get_days_since_reset.return_value = 5
        
        assert filter_alert.is_on is False

    def test_sensor_triggered_by_hours_threshold(self, filter_alert):
        """Test sensor is on when runtime hours exceed threshold."""
        filter_alert._runtime_manager.get_runtime_hours.return_value = 35.0
        filter_alert._runtime_manager.get_days_since_reset.return_value = 5
        
        assert filter_alert.is_on is True

    def test_sensor_triggered_by_days_threshold(self, filter_alert):
        """Test sensor is on when days since reset exceed threshold."""
        filter_alert._runtime_manager.get_runtime_hours.return_value = 10.0
        filter_alert._runtime_manager.get_days_since_reset.return_value = 95
        
        assert filter_alert.is_on is True

    def test_sensor_triggered_by_both_thresholds(self, filter_alert):
        """Test sensor is on when both thresholds exceeded."""
        filter_alert._runtime_manager.get_runtime_hours.return_value = 50.0
        filter_alert._runtime_manager.get_days_since_reset.return_value = 100
        
        assert filter_alert.is_on is True

    def test_sensor_with_no_reset_date_low_runtime(self, filter_alert):
        """Test sensor behavior with no reset date and low runtime."""
        filter_alert._runtime_manager.get_runtime_hours.return_value = 2.0
        filter_alert._runtime_manager.get_days_since_reset.return_value = None
        
        assert filter_alert.is_on is False

    def test_sensor_with_no_reset_date_high_runtime(self, filter_alert):
        """Test sensor behavior with no reset date and high runtime."""
        filter_alert._runtime_manager.get_runtime_hours.return_value = 10.0
        filter_alert._runtime_manager.get_days_since_reset.return_value = None
        
        assert filter_alert.is_on is True

    def test_sensor_extra_state_attributes(self, filter_alert):
        """Test sensor returns correct extra state attributes."""
        filter_alert._runtime_manager.get_runtime_hours.return_value = 20.0
        filter_alert._runtime_manager.get_days_since_reset.return_value = 15
        
        attrs = filter_alert.extra_state_attributes
        
        assert "runtime_hours" in attrs
        assert "days_since_reset" in attrs
        assert "hours_threshold" in attrs
        assert "days_threshold" in attrs
        assert attrs["runtime_hours"] == 20.0
        assert attrs["days_since_reset"] == 15
        assert attrs["hours_threshold"] == 30
        assert attrs["days_threshold"] == 90

    def test_sensor_device_class(self, filter_alert):
        """Test sensor has correct device class."""
        assert filter_alert.device_class == "problem"

    def test_sensor_name(self, filter_alert):
        """Test sensor name property."""
        # Entity uses translation key, not name property
        assert filter_alert._attr_translation_key == "filter_alert"

    @pytest.mark.asyncio
    async def test_sensor_handles_notify_update(self, filter_alert):
        """Test sensor updates on notify events."""
        filter_alert._runtime_manager.get_runtime_hours.return_value = 40.0
        filter_alert.schedule_update_ha_state = MagicMock()
        
        # Simulate notify event
        filter_alert._handle_notify("fan", {"Fan": {"fanonoff": 1}})
        
        # Should trigger state update
        filter_alert.schedule_update_ha_state.assert_called_once()

    def test_sensor_high_runtime_no_days(self, filter_alert):
        """Test sensor triggers on high runtime even without days."""
        filter_alert._runtime_manager.get_runtime_hours.return_value = 50.0
        filter_alert._runtime_manager.get_days_since_reset.return_value = None
        
        # Should trigger based on runtime alone
        assert filter_alert.is_on is True
