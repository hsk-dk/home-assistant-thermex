"""Tests for fan entity."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from custom_components.thermex_api.fan import ThermexFan


class TestFanSetup:
    """Test fan setup."""

    @pytest.mark.asyncio
    async def test_async_setup_entry(self, mock_hass, mock_hub, mock_config_entry):
        """Test fan setup from config entry."""
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
        
        with patch('custom_components.thermex_api.fan.entity_platform') as mock_platform:
            mock_current_platform = MagicMock()
            mock_platform.async_get_current_platform.return_value = mock_current_platform
            
            await async_setup_entry(mock_hass, mock_config_entry, async_add_entities)
            
            async_add_entities.assert_called_once()
            entities = async_add_entities.call_args[0][0]
            assert len(entities) == 1
            assert isinstance(entities[0], ThermexFan)


class TestThermexFan:
    """Test ThermexFan entity."""

    @pytest.fixture
    def fan_entity(self, mock_hub, mock_config_entry, mock_hass):
        """Create a ThermexFan entity."""
        runtime_manager = MagicMock()
        runtime_manager.get_runtime_hours = MagicMock(return_value=50.5)
        runtime_manager.get_days_since_reset = MagicMock(return_value=10)
        runtime_manager.get_last_preset = MagicMock(return_value="off")
        runtime_manager.get_filter_time = MagicMock(return_value=75)
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
        original_state = fan_entity._is_on
        
        with patch.object(fan_entity, 'async_write_ha_state'):
            fan_entity._handle_notify("light", {"Light": {"lightonoff": 1}})
        
        assert fan_entity._is_on == original_state

    def test_fan_extra_state_attributes(self, fan_entity):
        """Test fan extra state attributes."""
        attrs = fan_entity.extra_state_attributes
        
        assert "runtime_hours" in attrs
        assert "filter_time" in attrs
        assert attrs["runtime_hours"] == 50.5
        assert attrs["filter_time"] == 75

    @pytest.mark.asyncio
    async def test_fan_reset_service(self, fan_entity):
        """Test reset runtime service."""
        await fan_entity.async_reset()
        
        fan_entity._runtime_manager.reset.assert_called_once()
        fan_entity._runtime_manager.save.assert_called_once()

    @pytest.mark.asyncio
    async def test_fan_handle_notify_updates_state(self, fan_entity):
        """Test fan state updates from notifications."""
        with patch.object(fan_entity, 'async_write_ha_state'):
            fan_entity._handle_notify("fan", {
                "Fan": {
                    "fanspeed": 3,  # high
                    "fanstatus": 1,
                }
            })
            
            assert fan_entity.is_on is True
            assert fan_entity._preset_mode == "high"

    @pytest.mark.asyncio
    async def test_fan_handle_notify_off_stops_runtime(self, fan_entity):
        """Test fan stops runtime tracking when turned off."""
        fan_entity._is_on = True
        
        with patch.object(fan_entity, 'async_write_ha_state'):
            fan_entity._handle_notify("fan", {
                "Fan": {
                    "fanspeed": 0,
                    "fanstatus": 0,
                }
            })
            
            assert fan_entity.is_on is False
            fan_entity._runtime_manager.stop.assert_called_once()

    @pytest.mark.asyncio
    async def test_start_delayed_off(self, fan_entity, mock_hass):
        """Test starting delayed turn off."""
        fan_entity._is_on = True
        
        with patch('custom_components.thermex_api.fan.async_call_later') as mock_timer:
            await fan_entity.start_delayed_off()
            
            assert fan_entity._delayed_off_active is True
            mock_timer.assert_called()

    @pytest.mark.asyncio
    async def test_cancel_delayed_off(self, fan_entity):
        """Test canceling delayed turn off."""
        fan_entity._delayed_off_active = True
        fan_entity._delayed_off_handle = MagicMock()
        fan_entity._countdown_unsub = MagicMock()
        
        await fan_entity.cancel_delayed_off()
        
        assert fan_entity._delayed_off_active is False
        fan_entity._delayed_off_handle.assert_called_once()
        fan_entity._countdown_unsub.assert_called_once()

    @pytest.mark.asyncio
    async def test_delayed_off_execution(self, fan_entity, mock_hub):
        """Test delayed off actually turns fan off."""
        fan_entity._is_on = True
        
        with patch.object(fan_entity, 'async_turn_off', new_callable=AsyncMock) as mock_turn_off:
            await fan_entity._execute_delayed_off(None)
            
            mock_turn_off.assert_called_once()
            assert fan_entity._delayed_off_active is False