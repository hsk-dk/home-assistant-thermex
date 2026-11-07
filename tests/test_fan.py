"""Tests for the fan entity."""
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from custom_components.thermex_api.fan import ThermexFan
from custom_components.thermex_api.state import FanState, ThermexState


def _state(on: bool, speed: int) -> ThermexState:
    return ThermexState(fan=FanState(on=on, speed=speed))


@pytest.fixture
def fan(coordinator, mock_hass):
    entity = ThermexFan(coordinator)
    entity.hass = mock_hass
    entity.async_write_ha_state = MagicMock()
    return entity


class TestState:
    def test_is_the_main_entity_of_the_device(self, fan):
        assert fan.name is None
        assert fan.unique_id == "test_thermex_hub_fan"

    def test_off_has_no_preset_and_zero_percent(self, fan, coordinator):
        coordinator.data = _state(False, 0)

        assert (fan.is_on, fan.preset_mode, fan.percentage) == (False, None, 0)

    @pytest.mark.parametrize("speed,preset,percentage", [
        (1, "low", 25), (2, "medium", 50), (3, "high", 75), (4, "boost", 100),
    ])
    def test_levels_map_to_presets_and_percentages(self, fan, coordinator, speed, preset, percentage):
        coordinator.data = _state(True, speed)

        assert (fan.is_on, fan.preset_mode, fan.percentage) == (True, preset, percentage)

    def test_stale_speed_while_off_is_not_reported_as_preset(self, fan, coordinator):
        """The hood keeps the last speed after switching off."""
        coordinator.data = _state(False, 3)

        assert (fan.is_on, fan.preset_mode, fan.percentage) == (False, None, 0)

    def test_unknown_speed_has_no_preset(self, fan, coordinator):
        coordinator.data = _state(True, 9)

        assert fan.is_on is True
        assert fan.preset_mode is None
        assert fan.percentage is None

    def test_no_data_yet_counts_as_off(self, fan, coordinator):
        coordinator.data = None

        assert fan.is_on is False

    def test_presets_do_not_include_off(self, fan):
        assert fan.preset_modes == ["low", "medium", "high", "boost"]
        assert fan.speed_count == 4


class TestCommands:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("preset,speed", [("low", 1), ("medium", 2), ("high", 3), ("boost", 4)])
    async def test_set_preset_sends_the_level(self, fan, mock_hub, preset, speed):
        await fan.async_set_preset_mode(preset)

        mock_hub.send_update.assert_awaited_once_with({"Fan": {"fanonoff": 1, "fanspeed": speed}})

    @pytest.mark.asyncio
    @pytest.mark.parametrize("percentage,speed", [(1, 1), (25, 1), (26, 2), (51, 3), (76, 4), (100, 4)])
    async def test_percentage_selects_the_nearest_level(self, fan, mock_hub, percentage, speed):
        await fan.async_set_percentage(percentage)

        assert mock_hub.send_update.call_args.args[0]["Fan"]["fanspeed"] == speed

    @pytest.mark.asyncio
    async def test_zero_percent_turns_off(self, fan, mock_hub):
        await fan.async_set_percentage(0)

        mock_hub.send_update.assert_awaited_once_with({"Fan": {"fanonoff": 0, "fanspeed": 0}})

    @pytest.mark.asyncio
    async def test_turn_on_with_arguments(self, fan, mock_hub):
        await fan.async_turn_on(preset_mode="boost")
        assert mock_hub.send_update.call_args.args[0]["Fan"]["fanspeed"] == 4

        await fan.async_turn_on(percentage=50)
        assert mock_hub.send_update.call_args.args[0]["Fan"]["fanspeed"] == 2

    @pytest.mark.asyncio
    async def test_turn_on_defaults_to_medium_when_nothing_is_known(self, fan, mock_hub):
        await fan.async_turn_on()

        assert mock_hub.send_update.call_args.args[0]["Fan"]["fanspeed"] == 2

    @pytest.mark.asyncio
    async def test_turn_on_returns_to_the_last_level_in_use(self, fan, coordinator, mock_hub):
        coordinator.data = _state(True, 3)
        fan._handle_coordinator_update()
        coordinator.data = _state(False, 0)
        fan._handle_coordinator_update()

        await fan.async_turn_on()

        assert mock_hub.send_update.call_args.args[0]["Fan"]["fanspeed"] == 3

    def test_last_level_is_restored_from_storage(self, coordinator, runtime_manager):
        runtime_manager.get_last_preset.return_value = "boost"

        assert ThermexFan(coordinator)._last_active_preset == "boost"

    @pytest.mark.asyncio
    async def test_turn_off_cancels_the_delayed_turn_off_first(self, fan, mock_hub, delayed_off):
        order = []
        delayed_off.async_cancel.side_effect = lambda: order.append("cancel")
        mock_hub.send_update.side_effect = lambda body: order.append("update")

        await fan.async_turn_off()

        assert order == ["cancel", "update"]
        assert mock_hub.send_update.call_args.args[0] == {"Fan": {"fanonoff": 0, "fanspeed": 0}}

    @pytest.mark.asyncio
    async def test_state_is_not_assumed_after_a_command(self, fan, mock_hub):
        """The state comes from the coordinator (Status read-back), not from the command."""
        await fan.async_set_preset_mode("high")

        fan.async_write_ha_state.assert_not_called()
        assert fan.is_on is False


class TestActions:
    @pytest.mark.asyncio
    async def test_reset_runtime(self, fan, coordinator):
        await fan.async_reset()

        coordinator.async_reset_runtime.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_start_and_cancel_delayed_off(self, fan, delayed_off):
        await fan.start_delayed_off()
        await fan.cancel_delayed_off()

        delayed_off.async_start.assert_awaited_once()
        delayed_off.async_cancel.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_follows_the_delayed_off_timer(self, fan, delayed_off, mock_hass):
        from unittest.mock import patch

        from custom_components.thermex_api.entity import ThermexEntity

        fan.async_on_remove = MagicMock()
        with patch.object(ThermexEntity, "async_added_to_hass"):
            await fan.async_added_to_hass()

        delayed_off.async_add_listener.assert_called_once_with(fan.async_write_ha_state)
        fan.async_on_remove.assert_called_once_with(delayed_off.async_add_listener.return_value)


class TestAttributes:
    def test_runtime_and_filter_attributes(self, fan):
        attrs = fan.extra_state_attributes

        assert attrs["runtime_hours"] == 12.5
        assert attrs["filter_time"] == 12.5
        assert attrs["last_reset"] == "2026-01-15T10:00:00+00:00"
        assert attrs["threshold"] == 100
        assert attrs["alert"] is False
        assert attrs["delayed_off_active"] is False
        assert attrs["delayed_off_delay"] == 60
        assert "delayed_off_scheduled_time" not in attrs

    def test_never_reset_is_none_not_text(self, fan, runtime_manager):
        runtime_manager.get_last_reset.return_value = None

        assert fan.extra_state_attributes["last_reset"] is None

    def test_alert_when_the_threshold_is_reached(self, fan, runtime_manager):
        runtime_manager.get_runtime_hours.return_value = 100

        assert fan.extra_state_attributes["alert"] is True

    def test_delayed_off_attributes(self, fan, delayed_off):
        delayed_off.active = True
        delayed_off.remaining = 7
        delayed_off.scheduled_time = datetime(2026, 11, 7, 12, 0, tzinfo=timezone.utc)

        attrs = fan.extra_state_attributes

        assert attrs["delayed_off_active"] is True
        assert attrs["delayed_off_remaining"] == 7
        assert attrs["delayed_off_scheduled_time"] == "2026-11-07T12:00:00+00:00"

    def test_connection_details_are_not_attributes(self, fan):
        """They changed on every update; they are on the connection status sensor."""
        for key in ("connection_state", "last_error", "watchdog_active", "is_on", "last_preset"):
            assert key not in fan.extra_state_attributes


@pytest.mark.asyncio
async def test_setup_adds_the_fan(coordinator, mock_hass, mock_config_entry):
    from custom_components.thermex_api.fan import async_setup_entry

    mock_config_entry.runtime_data = MagicMock(coordinator=coordinator)
    add = MagicMock()

    await async_setup_entry(mock_hass, mock_config_entry, add)

    assert [type(e) for e in add.call_args.args[0]] == [ThermexFan]
