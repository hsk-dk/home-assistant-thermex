"""Tests for fan entity."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from custom_components.thermex_api.fan import ThermexFan


class TestThermexFan:
    """Test ThermexFan entity."""

    @pytest.fixture
    def fan_entity(self, mock_hub, mock_config_entry, mock_hass):
        """Create a ThermexFan entity."""
        runtime_manager = MagicMock()
        runtime_manager.get_runtime_hours = MagicMock(return_value=50.5)
        runtime_manager.get_days_since_reset = MagicMock(return_value=10)
        runtime_manager.get_last_preset = MagicMock(return_value="off")
        runtime_manager.start = MagicMock()
        runtime_manager.stop = MagicMock()
        runtime_manager.reset = MagicMock()
        runtime_manager.save = AsyncMock()
        runtime_manager.set_last_preset = MagicMock()
        
        fan = ThermexFan(mock_hub, runtime_manager, mock_config_entry)
        fan.hass = mock_hass
        return fan

    def test_fan_initialization(self, fan_entity, mock_hub):
        """Test fan entity initialization."""
        assert fan_entity._hub == mock_hub
        assert fan_entity._preset_mode == "off"
        assert fan_entity.is_on is False

    def test_fan_preset_modes(self, fan_entity):
        """Test fan has correct preset modes."""
        assert "off" in fan_entity.preset_modes
        assert "low" in fan_entity.preset_modes
        assert "medium" in fan_entity.preset_modes
        assert "high" in fan_entity.preset_modes
        assert "boost" in fan_entity.preset_modes

    @pytest.mark.asyncio
    async def test_fan_turn_on_default(self, fan_entity, mock_hub):
        """Test turning on fan with default preset."""
        await fan_entity.async_turn_on()
        
        mock_hub.send_request.assert_called_once()
        call_args = mock_hub.send_request.call_args[0]
        assert call_args[0] == "Update"
        assert call_args[1]["Fan"]["fanspeed"] == 2  # medium is default

    @pytest.mark.asyncio
    async def test_fan_turn_on_with_preset(self, fan_entity, mock_hub):
        """Test turning on fan with specific preset."""
        await fan_entity.async_turn_on(preset_mode="boost")
        
        mock_hub.send_request.assert_called_once()
        call_args = mock_hub.send_request.call_args[0]
        assert call_args[1]["Fan"]["fanspeed"] == 4  # boost

    @pytest.mark.asyncio
    async def test_fan_turn_off(self, fan_entity, mock_hub):
        """Test turning off fan."""
        fan_entity._is_on = True
        fan_entity._preset_mode = "high"
        
        await fan_entity.async_turn_off()
        
        mock_hub.send_request.assert_called_once()
        call_args = mock_hub.send_request.call_args[0]
        assert call_args[1]["Fan"]["fanspeed"] == 0

    @pytest.mark.asyncio
    async def test_fan_set_preset_mode(self, fan_entity, mock_hub):
        """Test setting fan preset mode."""
        await fan_entity.async_set_preset_mode("low")
        
        mock_hub.send_request.assert_called_once()
        call_args = mock_hub.send_request.call_args[0]
        assert call_args[1]["Fan"]["fanspeed"] == 1  # low

    def test_fan_handle_notify_ignores_wrong_type(self, fan_entity):
        """Test fan ignores non-fan notifications."""
        original_state = fan_entity._preset_mode
        
        fan_entity._handle_notify("light", {"Light": {"lightonoff": 1}})
        
        assert fan_entity._preset_mode == original_state

    def test_fan_extra_state_attributes(self, fan_entity):
        """Test fan extra state attributes."""
        attrs = fan_entity.extra_state_attributes
        
        assert "runtime_hours" in attrs
        assert "filter_time" in attrs
        assert attrs["runtime_hours"] == 50.5

    @pytest.mark.asyncio
    async def test_fan_reset_service(self, fan_entity):
        """Test reset runtime service."""
        await fan_entity.async_reset()
        
        fan_entity._runtime_manager.reset.assert_called_once()
        fan_entity._runtime_manager.save.assert_called_once()
