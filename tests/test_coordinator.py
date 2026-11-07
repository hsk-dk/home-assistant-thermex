"""The coordinator: shared state, runtime counting, availability of the first refresh."""
from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.helpers.update_coordinator import UpdateFailed

from custom_components.thermex_api.coordinator import ThermexCoordinator
from custom_components.thermex_api.state import FanState, ThermexState

ON = {"Fan": {"fanonoff": 1, "fanspeed": 2}}
OFF = {"Fan": {"fanonoff": 0, "fanspeed": 0}}


@pytest.fixture
def runtime():
    rm = MagicMock()
    rm.get_last_reset = MagicMock(return_value="2026-01-01T00:00:00+00:00")
    rm.get_last_preset = MagicMock(return_value="off")
    rm.save = AsyncMock()
    return rm


@pytest.fixture
def coord(mock_hass, mock_hub, mock_config_entry, runtime):
    mock_hass.async_create_task = MagicMock(side_effect=lambda coro, name=None: coro.close())
    c = ThermexCoordinator(mock_hass, mock_config_entry, mock_hub, runtime)
    c.async_set_updated_data = MagicMock(side_effect=lambda data: setattr(c, "data", data))
    c.delayed_off = MagicMock()
    return c


def test_status_updates_the_shared_state(coord):
    coord._handle_status(ON)

    assert coord.data.fan == FanState(on=True, speed=2)
    assert coord.fan_running is True
    coord.async_set_updated_data.assert_called_once()


def test_listens_to_the_hoods_signal_and_stops_on_unload(mock_hass, mock_hub, mock_config_entry, runtime):
    from unittest.mock import patch

    with patch("custom_components.thermex_api.coordinator.async_dispatcher_connect") as connect:
        ThermexCoordinator(mock_hass, mock_config_entry, mock_hub, runtime)

    assert connect.call_args.args[1] == mock_hub.signal
    mock_config_entry.async_on_unload.assert_any_call(connect.return_value)


@pytest.mark.asyncio
async def test_first_refresh_asks_the_hood_for_everything(coord, mock_hub):
    mock_hub.send_request = AsyncMock(return_value={"Status": 200, "Data": {
        **ON, "Light": {"lightonoff": 1, "lightbrightness": 50},
    }})

    state = await coord._async_update_data()

    mock_hub.send_request.assert_awaited_once_with("status", {})
    assert state.fan.running and state.light.brightness == 50


@pytest.mark.asyncio
@pytest.mark.parametrize("error", [ConnectionError("down"), TimeoutError()])
async def test_unreachable_hood_fails_the_refresh_with_a_translated_error(coord, mock_hub, error):
    mock_hub.send_request = AsyncMock(side_effect=error)

    with pytest.raises(UpdateFailed) as exc:
        await coord._async_update_data()

    assert exc.value.translation_key == "cannot_connect"
    assert exc.value.translation_placeholders == {"host": "192.168.1.100"}


class TestRuntimeCounting:
    def test_session_starts_when_the_fan_starts(self, coord, runtime):
        coord._handle_status(ON)

        runtime.start.assert_called_once()
        runtime.stop.assert_not_called()

    def test_session_stops_when_the_fan_stops(self, coord, runtime):
        coord._handle_status(ON)
        coord._handle_status(OFF)

        runtime.stop.assert_called_once()
        coord.delayed_off.cancel_soon.assert_called_once()

    def test_heartbeats_do_not_touch_the_counter_or_storage(self, coord, runtime):
        coord._handle_status(ON)
        runtime.get_last_preset.return_value = "medium"  # as stored by the first update
        runtime.start.reset_mock()
        runtime.save.reset_mock()
        coord.hass.async_create_task.reset_mock()

        coord._handle_status(ON)

        runtime.start.assert_not_called()
        coord.hass.async_create_task.assert_not_called()

    def test_changes_are_saved(self, coord, runtime):
        coord._handle_status(ON)

        coord.hass.async_create_task.assert_called_once()

    def test_first_ever_run_records_the_reset_date_and_keeps_counting(self, coord, runtime):
        runtime.get_last_reset.return_value = None

        coord._handle_status(ON)

        runtime.reset.assert_called_once()
        assert runtime.start.call_count == 2  # restarted: reset closes the session

    def test_last_level_in_use_is_remembered_but_off_is_not(self, coord, runtime):
        coord._handle_status(ON)
        runtime.set_last_preset.assert_called_once_with("medium")

        runtime.set_last_preset.reset_mock()
        coord._handle_status(OFF)
        runtime.set_last_preset.assert_not_called()

    def test_other_sections_do_not_affect_the_counter(self, coord, runtime):
        coord._handle_status({"Light": {"lightonoff": 1, "lightbrightness": 50}})

        runtime.start.assert_not_called()
        runtime.stop.assert_not_called()

    @pytest.mark.asyncio
    async def test_reset_while_running_keeps_counting(self, coord, runtime):
        coord._handle_status(ON)
        runtime.start.reset_mock()
        coord.async_update_listeners = MagicMock()

        await coord.async_reset_runtime()

        runtime.reset.assert_called_once()
        runtime.start.assert_called_once()
        runtime.save.assert_awaited()
        coord.async_update_listeners.assert_called_once()

    @pytest.mark.asyncio
    async def test_reset_while_stopped_does_not_start_a_session(self, coord, runtime):
        coord.async_update_listeners = MagicMock()

        await coord.async_reset_runtime()

        runtime.start.assert_not_called()


def test_fan_running_is_false_before_any_data(coord):
    coord.data = None
    assert coord.fan_running is False

    coord.data = ThermexState()
    assert coord.fan_running is False
