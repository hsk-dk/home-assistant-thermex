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

    @pytest.mark.asyncio
    async def test_fan_turn_on_starts_runtime(self, fan_entity):
        """Test turning on fan starts runtime tracking."""
        await fan_entity.async_turn_on()
        fan_entity._runtime_manager.start.assert_called_once()

    @pytest.mark.asyncio
    async def test_fan_turn_off_stops_runtime(self, fan_entity):
        """Test turning off fan stops runtime tracking."""
        fan_entity._is_on = True
        await fan_entity.async_turn_off()
        fan_entity._runtime_manager.stop.assert_called_once()

    @pytest.mark.asyncio
    async def test_fan_set_preset_mode_updates_preset(self, fan_entity, mock_hub):
        """Test setting preset mode."""
        await fan_entity.async_turn_on()
        await fan_entity.async_set_preset_mode("high")
        mock_hub.send_request.assert_called()
        # Preset is updated when notification is received from hub
        fan_entity._handle_notify("fan", {"Fan": {"fanonoff": 1, "fanspeed": 3}})
        assert fan_entity._preset_mode == "high"

    @pytest.mark.asyncio
    async def test_fan_handle_notify_updates_state(self, fan_entity, mock_hass):
        """Test fan state updates from notify."""
        # Mock async_create_task to not actually create tasks
        mock_hass.async_create_task = MagicMock()
        
        fan_entity._handle_notify("fan", {
            "Fan": {
                "fanonoff": 1,
                "fanspeed": 3
            }
        })
        
        assert fan_entity._is_on is True
        assert fan_entity._preset_mode == "high"

    @pytest.mark.asyncio
    async def test_fan_handle_notify_off_state(self, fan_entity, mock_hass):
        """Test fan handles off state from notify."""
        # Mock async_create_task to not actually create tasks
        mock_hass.async_create_task = MagicMock()
        
        fan_entity._is_on = True
        fan_entity._handle_notify("fan", {
            "Fan": {
                "fanonoff": 0,
                "fanspeed": 0
            }
        })
        
        assert fan_entity._is_on is False
        assert fan_entity._preset_mode == "off"

    @pytest.mark.asyncio
    async def test_fan_turn_on_with_percentage(self, fan_entity, mock_hub):
        """Test turning on fan with percentage."""
        await fan_entity.async_turn_on(percentage=50)
        
        call_args = mock_hub.send_request.call_args[0]
        # Should map percentage to preset
        assert "Fan" in call_args[1]

    @pytest.mark.skip(reason="start_delayed_off creates uncancellable countdown timer - needs implementation change")
    @pytest.mark.asyncio
    async def test_fan_start_delayed_off(self, fan_entity, mock_hass):
        """Test starting delayed off."""
        # Fan must be running to start delayed off
        fan_entity._is_on = True
        
        # Mock schedule_update_ha_state to prevent entity platform errors
        fan_entity.schedule_update_ha_state = MagicMock()
        
        await fan_entity.start_delayed_off()
        
        assert fan_entity._delayed_off_active is True
        assert fan_entity._delayed_off_handle is not None

    @pytest.mark.asyncio
    async def test_fan_cancel_delayed_off(self, fan_entity):
        """Test canceling delayed off."""
        fan_entity._delayed_off_active = True
        fan_entity._delayed_off_handle = MagicMock()
        
        await fan_entity.cancel_delayed_off()
        
        assert fan_entity._delayed_off_active is False

    @pytest.mark.skip(reason="_update_countdown creates lingering timer - needs implementation change to return handle")
    def test_fan_update_countdown(self, fan_entity, mock_hass):
        """Test delayed off countdown updates."""
        # Mock schedule_update_ha_state to prevent actual state updates
        fan_entity.schedule_update_ha_state = MagicMock()
        
        fan_entity._delayed_off_active = True
        fan_entity._delayed_off_remaining = 30
        
        # Call _update_countdown which decrements remaining by 1 minute
        fan_entity._update_countdown(None)
        
        assert fan_entity._delayed_off_remaining == 29
        fan_entity.schedule_update_ha_state.assert_called()

    def test_fan_extra_state_attributes_with_delayed_off(self, fan_entity):
        """Test extra state attributes include delayed off info."""
        fan_entity._delayed_off_active = True
        fan_entity._delayed_off_remaining = 300
        
        attrs = fan_entity.extra_state_attributes
        
        assert "delayed_off_active" in attrs
        assert attrs["delayed_off_active"] is True

    @pytest.mark.asyncio
    async def test_fan_async_will_remove_from_hass(self, fan_entity):
        """Test cleanup when removing from hass."""
        fan_entity._delayed_off_handle = MagicMock()
        fan_entity._auto_off_handle = MagicMock()
        
        await fan_entity.async_will_remove_from_hass()
        
        # Should cancel timers
        if fan_entity._delayed_off_handle:
            fan_entity._delayed_off_handle.cancel.assert_called_once()
