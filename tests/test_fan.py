"""Tests for fan entity."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from homeassistant.components.fan import DOMAIN as FAN_DOMAIN

from custom_components.thermex_api.fan import ThermexFan
from custom_components.thermex_api.const import DOMAIN


class TestThermexFan:
    """Test ThermexFan entity."""

    @pytest.fixture
    def fan_entity(self, mock_hub, mock_config_entry):
        """Create a ThermexFan entity."""
        runtime_manager = MagicMock()
        runtime_manager.get_runtime_hours = MagicMock(return_value=50.5)
        runtime_manager.get_days_since_reset = MagicMock(return_value=10)
        
        fan = ThermexFan(mock_hub, runtime_manager, mock_config_entry)
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

    def test_fan_handle_notify_updates_state(self, fan_entity):
        """Test fan state updates from notifications."""
        fan_entity._handle_notify("fan", {
            "Fan": {
                "fanspeed": 3,  # high
                "fanstatus": 1,
            }
        })
        
        assert fan_entity.is_on is True
        assert fan_entity._preset_mode == "high"

    def test_fan_handle_notify_ignores_wrong_type(self, fan_entity):
        """Test fan ignores non-fan notifications."""
        original_state = fan_entity._preset_mode
        
        fan_entity._handle_notify("light", {"Light": {"lightonoff": 1}})
        
        assert fan_entity._preset_mode == original_state

    def test_fan_extra_state_attributes(self, fan_entity):
        """Test fan extra state attributes."""
        attrs = fan_entity.extra_state_attributes
        
        assert "runtime_hours" in attrs
        assert "days_since_reset" in attrs
        assert attrs["runtime_hours"] == 50.5
        assert attrs["days_since_reset"] == 10

    @pytest.mark.asyncio
    async def test_fan_reset_service(self, fan_entity):
        """Test reset runtime service."""
        runtime_manager = fan_entity._runtime_manager
        runtime_manager.reset_runtime = AsyncMock()
        
        await fan_entity.async_reset()
        
        runtime_manager.reset_runtime.assert_called_once()

    @pytest.mark.asyncio
    async def test_fan_delayed_off_starts_timer(self, fan_entity, mock_hass):
        """Test delayed turn off starts countdown."""
        fan_entity.hass = mock_hass
        fan_entity._config_entry.options = {"fan_auto_off_delay": 30}
        
        with patch("custom_components.thermex_api.fan.async_call_later") as mock_timer:
            await fan_entity.start_delayed_off()
            
            assert fan_entity._delayed_off_task is not None
            mock_timer.assert_called()

    @pytest.mark.asyncio
    async def test_fan_cancel_delayed_off(self, fan_entity):
        """Test canceling delayed turn off."""
        fan_entity._delayed_off_task = MagicMock()
        fan_entity._countdown_unsub = MagicMock()
        
        await fan_entity.cancel_delayed_off()
        
        fan_entity._delayed_off_task.assert_called_once()
        fan_entity._countdown_unsub.assert_called_once()
        assert fan_entity._delayed_off_seconds is None
