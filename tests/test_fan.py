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
        assert "off" not in fan_entity.preset_modes  # off is not a preset
        assert "low" in fan_entity.preset_modes
        assert "medium" in fan_entity.preset_modes
        assert "high" in fan_entity.preset_modes
        assert "boost" in fan_entity.preset_modes

    @pytest.mark.asyncio
    async def test_fan_turn_on_default(self, fan_entity, mock_hub):
        """Test turning on fan with default preset."""
        await fan_entity.async_turn_on()
        
        mock_hub.send_update.assert_called_once()
        call_args = mock_hub.send_update.call_args[0]
        assert call_args[0]["Fan"]["fanspeed"] == 2  # medium is default

    @pytest.mark.asyncio
    async def test_fan_turn_on_with_preset(self, fan_entity, mock_hub):
        """Test turning on fan with specific preset."""
        await fan_entity.async_turn_on(preset_mode="boost")
        
        mock_hub.send_update.assert_called_once()
        call_args = mock_hub.send_update.call_args[0]
        assert call_args[0]["Fan"]["fanspeed"] == 4  # boost

    @pytest.mark.asyncio
    async def test_fan_turn_off(self, fan_entity, mock_hub):
        """Test turning off fan."""
        fan_entity._is_on = True
        fan_entity._preset_mode = "high"
        
        await fan_entity.async_turn_off()
        
        mock_hub.send_update.assert_called_once()
        call_args = mock_hub.send_update.call_args[0]
        assert call_args[0]["Fan"]["fanspeed"] == 0

    @pytest.mark.asyncio
    async def test_fan_set_preset_mode(self, fan_entity, mock_hub):
        """Test setting fan preset mode."""
        await fan_entity.async_set_preset_mode("low")
        
        mock_hub.send_update.assert_called_once()
        call_args = mock_hub.send_update.call_args[0]
        assert call_args[0]["Fan"]["fanspeed"] == 1  # low

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
        """Runtime tracking starts when the hood reports the fan running."""
        await fan_entity.async_turn_on()
        # Commands never start tracking themselves: the Status read-back does
        fan_entity._runtime_manager.start.assert_not_called()

        fan_entity._handle_notify("fan", {"Fan": {"fanonoff": 1, "fanspeed": 2}})

        fan_entity._runtime_manager.start.assert_called_once()

    @pytest.mark.asyncio
    async def test_fan_turn_off_stops_runtime(self, fan_entity):
        """Runtime tracking stops when the hood reports the fan off."""
        fan_entity._is_on = True
        await fan_entity.async_turn_off()
        fan_entity._runtime_manager.stop.assert_not_called()

        fan_entity._handle_notify("fan", {"Fan": {"fanonoff": 0, "fanspeed": 0}})

        fan_entity._runtime_manager.stop.assert_called_once()

    def test_heartbeat_status_does_not_rewrite_storage(self, fan_entity):
        """An unchanged Status (every 30 s heartbeat) must not save the runtime file."""
        fan_entity.hass.async_create_task = MagicMock()
        fan_entity._runtime_manager.get_last_reset = MagicMock(return_value="2026-01-01T00:00:00+00:00")
        fan_entity._runtime_manager.get_last_preset = MagicMock(return_value="off")
        fan_entity.schedule_update_ha_state = MagicMock()

        fan_entity._handle_notify("fan", {"Fan": {"fanonoff": 0, "fanspeed": 0}})
        fan_entity._handle_notify("fan", {"Fan": {"fanonoff": 0, "fanspeed": 0}})

        fan_entity.hass.async_create_task.assert_not_called()

    def test_changed_status_saves_storage_once(self, fan_entity):
        fan_entity.hass.async_create_task = MagicMock(side_effect=lambda coro: coro.close())
        fan_entity._runtime_manager.get_last_reset = MagicMock(return_value="2026-01-01T00:00:00+00:00")
        fan_entity._runtime_manager.get_last_preset = MagicMock(return_value="off")
        fan_entity.schedule_update_ha_state = MagicMock()

        fan_entity._handle_notify("fan", {"Fan": {"fanonoff": 1, "fanspeed": 3}})

        assert fan_entity.hass.async_create_task.call_count == 1

    @pytest.mark.asyncio
    async def test_fan_set_preset_mode_updates_preset(self, fan_entity, mock_hub):
        """Test setting preset mode."""
        await fan_entity.async_turn_on()
        await fan_entity.async_set_preset_mode("high")
        mock_hub.send_update.assert_called()
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
        
        call_args = mock_hub.send_update.call_args[0]
        # Should map percentage to preset
        assert "Fan" in call_args[0]

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
        
        await fan_entity.async_will_remove_from_hass()
        
        # Should cancel timers
        if fan_entity._delayed_off_handle:
            fan_entity._delayed_off_handle.cancel.assert_called_once()

    def test_fan_percentage_property(self, fan_entity):
        """Test percentage property returns 0 by default."""
        # Fan has percentage property but uses presets instead
        assert fan_entity.percentage == 0

    def test_fan_scheduled_time_in_attributes(self, fan_entity):
        """Test scheduled time appears in attributes."""
        from datetime import datetime, timedelta
        from homeassistant.util import dt as dt_util
        
        scheduled_time = dt_util.now() + timedelta(minutes=45)
        fan_entity._delayed_off_scheduled_time = scheduled_time
        
        attrs = fan_entity.extra_state_attributes
        assert "delayed_off_scheduled_time" in attrs
        assert attrs["delayed_off_scheduled_time"] == scheduled_time.isoformat()

    @pytest.mark.asyncio
    async def test_fan_turn_on_no_preset(self, fan_entity, mock_hub):
        """Test turning on fan when no preset mode is set."""
        fan_entity._preset_mode = "off"
        
        await fan_entity.async_turn_on()
        
        # Should use default "medium"
        call_args = mock_hub.send_update.call_args[0]
        assert call_args[0]["Fan"]["fanspeed"] == 2  # medium



    def test_fan_update_countdown_inactive(self, fan_entity):
        """Test _update_countdown does nothing when inactive."""
        fan_entity._delayed_off_active = False
        fan_entity._delayed_off_remaining = 30
        fan_entity.schedule_update_ha_state = MagicMock()
        
        fan_entity._update_countdown()
        
        # Should not update state when inactive
        fan_entity.schedule_update_ha_state.assert_not_called()

    def test_fan_update_countdown_zero_remaining(self, fan_entity):
        """Test _update_countdown handles zero remaining time."""
        fan_entity._delayed_off_active = True
        fan_entity._delayed_off_remaining = 0
        fan_entity.schedule_update_ha_state = MagicMock()
        
        fan_entity._update_countdown()
        
        # Should not schedule next update when at zero
        fan_entity.schedule_update_ha_state.assert_not_called()

    def test_fan_update_countdown_active_with_remaining(self, fan_entity):
        """Test _update_countdown schedules next update when active."""
        fan_entity._delayed_off_active = True
        fan_entity._delayed_off_remaining = 5
        fan_entity.schedule_update_ha_state = MagicMock()
        
        with patch('custom_components.thermex_api.fan.async_call_later') as mock_call_later:
            fan_entity._update_countdown()
            
            # Should decrement and schedule next update
            assert fan_entity._delayed_off_remaining == 4
            fan_entity.schedule_update_ha_state.assert_called_once()
            mock_call_later.assert_called_once()

    @pytest.mark.asyncio
    async def test_fan_handle_delayed_off(self, fan_entity, mock_hub):
        """Test _handle_delayed_off turns off fan and clears state."""
        fan_entity._delayed_off_active = True
        fan_entity._delayed_off_remaining = 1
        fan_entity._delayed_off_handle = MagicMock()
        fan_entity._delayed_off_scheduled_time = "2026-01-18T12:00:00Z"
        fan_entity._is_on = True
        fan_entity.schedule_update_ha_state = MagicMock()
        
        with patch('custom_components.thermex_api.fan.async_dispatcher_send') as mock_send:
            await fan_entity._handle_delayed_off(None)
            
            # Should clear delayed off state
            assert fan_entity._delayed_off_active is False
            assert fan_entity._delayed_off_remaining == 0
            assert fan_entity._delayed_off_handle is None
            assert fan_entity._delayed_off_scheduled_time is None
            
            # Should turn off fan
            mock_hub.send_update.assert_called_once()
            fan_entity.schedule_update_ha_state.assert_called()
            # Dispatcher called twice: once in async_turn_off, once in _handle_delayed_off
            assert mock_send.call_count == 2

    @pytest.mark.asyncio
    async def test_fan_start_delayed_off_service(self, fan_entity, mock_hub):
        """Test start_delayed_off service method."""
        fan_entity._is_on = True
        fan_entity._entry.options = {"fan_auto_off_delay": 15}
        fan_entity.schedule_update_ha_state = MagicMock()
        
        with patch('custom_components.thermex_api.fan.async_call_later') as mock_call_later:
            with patch('custom_components.thermex_api.fan.async_dispatcher_send') as mock_send:
                await fan_entity.start_delayed_off()
                
                # Should set delayed off state
                assert fan_entity._delayed_off_active is True
                assert fan_entity._delayed_off_remaining == 15
                assert fan_entity._delayed_off_scheduled_time is not None
                
                # Should schedule turn-off and countdown
                assert mock_call_later.call_count == 2  # delayed off + countdown
                mock_send.assert_called()
                # Called twice: once in start_delayed_off, potentially once in cancel_delayed_off
                assert fan_entity.schedule_update_ha_state.call_count >= 1

    @pytest.mark.asyncio
    async def test_fan_start_delayed_off_when_not_running(self, fan_entity):
        """start_delayed_off on a fan that is off is a user error, not a silent no-op."""
        from homeassistant.exceptions import ServiceValidationError

        fan_entity._is_on = False

        with pytest.raises(ServiceValidationError) as exc:
            await fan_entity.start_delayed_off()

        assert exc.value.translation_key == "fan_not_running"
        assert fan_entity._delayed_off_active is False

    @pytest.mark.asyncio
    async def test_fan_start_delayed_off_cancels_existing(self, fan_entity, mock_hub):
        """Test start_delayed_off cancels existing delayed off."""
        fan_entity._is_on = True
        fan_entity._delayed_off_active = True
        # The handle is a callable, not a mock with cancel()
        mock_handle = MagicMock()
        fan_entity._delayed_off_handle = mock_handle
        fan_entity._entry.options = {"fan_auto_off_delay": 10}
        
        with patch('custom_components.thermex_api.fan.async_call_later'):
            with patch('custom_components.thermex_api.fan.async_dispatcher_send'):
                await fan_entity.start_delayed_off()
                
                # Should have called the handle (not handle.cancel)
                mock_handle.assert_called_once()

    @pytest.mark.asyncio
    async def test_fan_fallback_status_with_data(self, fan_entity, mock_hub):
        """Test fan processes fallback status data."""
        fan_entity._got_initial_state = False
        mock_hub.startup_complete = False
        mock_hub.request_fallback_status = AsyncMock(return_value={
            "Fan": {
                "fanonoff": 1,
                "fanspeed": 2
            }
        })
        fan_entity.schedule_update_ha_state = MagicMock()
        
        await fan_entity._fallback_status(None)
        
        assert fan_entity._got_initial_state is True
        assert fan_entity._is_on is True
        assert fan_entity._preset_mode == "medium"

    @pytest.mark.asyncio
    async def test_fan_fallback_status_no_fan_data(self, fan_entity, mock_hub):
        """Test fan handles fallback status with no fan data."""
        fan_entity._got_initial_state = False
        mock_hub.startup_complete = False
        mock_hub.request_fallback_status = AsyncMock(return_value={})
        
        await fan_entity._fallback_status(None)
        
        assert fan_entity._got_initial_state is True

    @pytest.mark.asyncio
    async def test_fan_fallback_status_error(self, fan_entity, mock_hub):
        """Test fan handles fallback status error."""
        fan_entity._got_initial_state = False
        mock_hub.startup_complete = False
        mock_hub.request_fallback_status = AsyncMock(side_effect=Exception("Test error"))
        
        await fan_entity._fallback_status(None)
        
        # Should mark as got state even on error
        assert fan_entity._got_initial_state is True

    @pytest.mark.asyncio
    async def test_fan_fallback_status_startup_complete(self, fan_entity, mock_hub):
        """Test fan fallback when startup is complete."""
        fan_entity._got_initial_state = False
        mock_hub.startup_complete = True
        
        await fan_entity._fallback_status(None)
        
        # Should mark as got state without requesting
        assert fan_entity._got_initial_state is True

    @pytest.mark.asyncio
    async def test_fan_async_will_remove_from_hass(self, fan_entity):
        """Test fan cleanup when removed."""
        mock_cancel = MagicMock()
        fan_entity._delayed_off_handle = mock_cancel

        with patch('custom_components.thermex_api.fan.async_dispatcher_send'):
            await fan_entity.async_will_remove_from_hass()

        # Should cancel the delayed off timer (the dispatcher unsubscribe is
        # registered with async_on_remove by the base entity)
        mock_cancel.assert_called_once()
        assert fan_entity._delayed_off_handle is None

    @pytest.mark.asyncio
    async def test_fan_first_on_resets_runtime(self, fan_entity, mock_hub):
        """Test fan resets runtime on first turn on."""
        fan_entity._runtime_manager.get_last_reset.return_value = None
        
        # Simulate first notify when turning on
        fan_entity._handle_notify("fan", {
            "Fan": {
                "fanonoff": 1,
                "fanspeed": 2
            }
        })
        
        # Should have called reset
        fan_entity._runtime_manager.reset.assert_called_once()


class TestFanCountdownTimer:
    """Regression tests: cancelling must stop the countdown chain."""

    @pytest.fixture
    def fan_entity(self, mock_hub, mock_config_entry, mock_hass):
        runtime_manager = MagicMock()
        runtime_manager.get_last_preset = MagicMock(return_value="off")
        fan = ThermexFan(mock_hub, runtime_manager, mock_config_entry)
        fan.hass = mock_hass
        return fan

    @pytest.mark.asyncio
    async def test_cancel_stops_countdown_timer(self, fan_entity):
        fan_entity._is_on = True
        fan_entity.schedule_update_ha_state = MagicMock()
        cancel_off, cancel_count = MagicMock(), MagicMock()

        with patch("custom_components.thermex_api.fan.async_call_later", side_effect=[cancel_off, cancel_count]),              patch("custom_components.thermex_api.fan.async_dispatcher_send"):
            await fan_entity.start_delayed_off()
            await fan_entity.cancel_delayed_off()

        cancel_off.assert_called_once()
        cancel_count.assert_called_once()
        assert fan_entity._countdown_handle is None


def test_fan_is_the_main_entity_of_the_device(mock_hub, mock_config_entry):
    """Named after the device (name=None) so it does not read 'Thermex Hood Hood'."""
    from custom_components.thermex_api.fan import ThermexFan

    runtime_manager = MagicMock()
    runtime_manager.get_last_preset = MagicMock(return_value="off")

    fan = ThermexFan(mock_hub, runtime_manager, mock_config_entry)

    assert fan.name is None


class TestFanLevels:
    """Presets are the hood's four levels and always match the speed."""

    @pytest.fixture
    def fan(self, mock_hub, mock_config_entry, mock_hass):
        runtime_manager = MagicMock()
        runtime_manager.get_last_preset = MagicMock(return_value="off")
        runtime_manager.get_last_reset = MagicMock(return_value="x")
        runtime_manager.get_runtime_hours = MagicMock(return_value=1.0)
        runtime_manager.get_filter_time = MagicMock(return_value=1.0)
        runtime_manager.save = AsyncMock()
        entity = ThermexFan(mock_hub, runtime_manager, mock_config_entry)
        entity.hass = MagicMock()
        entity.hass.async_create_task = MagicMock(side_effect=lambda coro: coro.close())
        entity.schedule_update_ha_state = MagicMock()
        return entity

    def test_preset_none_and_percentage_zero_when_off(self, fan):
        assert fan.preset_mode is None
        assert fan.percentage == 0

    @pytest.mark.parametrize("speed,preset,pct", [(1, "low", 25), (2, "medium", 50), (3, "high", 75), (4, "boost", 100)])
    def test_levels_map_to_presets_and_percentages(self, fan, speed, preset, pct):
        fan._handle_notify("fan", {"Fan": {"fanonoff": 1, "fanspeed": speed}})

        assert fan.preset_mode == preset
        assert fan.percentage == pct

    def test_stale_speed_while_off_is_not_reported_as_preset(self, fan):
        fan._handle_notify("fan", {"Fan": {"fanonoff": 0, "fanspeed": 3}})

        assert fan.is_on is False
        assert fan.preset_mode is None
        assert fan.percentage == 0

    @pytest.mark.parametrize("pct,speed", [(1, 1), (25, 1), (26, 2), (50, 2), (51, 3), (75, 3), (76, 4), (100, 4)])
    @pytest.mark.asyncio
    async def test_set_percentage_uses_the_matching_level(self, fan, mock_hub, pct, speed):
        await fan.async_set_percentage(pct)

        assert mock_hub.send_update.call_args[0][0]["Fan"] == {"fanonoff": 1, "fanspeed": speed}

    @pytest.mark.asyncio
    async def test_turn_on_returns_to_the_last_level_in_use(self, fan, mock_hub):
        fan._handle_notify("fan", {"Fan": {"fanonoff": 1, "fanspeed": 3}})
        fan._handle_notify("fan", {"Fan": {"fanonoff": 0, "fanspeed": 0}})

        await fan.async_turn_on()

        assert mock_hub.send_update.call_args[0][0]["Fan"]["fanspeed"] == 3

    @pytest.mark.asyncio
    async def test_turn_on_defaults_to_medium(self, fan, mock_hub):
        await fan.async_turn_on()

        assert mock_hub.send_update.call_args[0][0]["Fan"]["fanspeed"] == 2

    def test_attributes_no_longer_carry_connection_noise(self, fan):
        attrs = fan.extra_state_attributes

        for key in ("connection_state", "last_error", "watchdog_active", "time_since_activity",
                    "heartbeat_interval", "connection_timeout", "is_on", "last_preset"):
            assert key not in attrs
        assert "runtime_hours" in attrs and "delayed_off_active" in attrs

    def test_slow_attributes_are_not_recorded(self, fan):
        assert {"runtime_hours", "delayed_off_remaining"} <= fan._unrecorded_attributes
