"""The delayed turn-off: persisted, resumed after reloads, cancelled when the fan stops."""
from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.util import dt as dt_util

from custom_components.thermex_api.delayed_off import DelayedOffManager
from custom_components.thermex_api.runtime_manager import RuntimeManager


@pytest.fixture
def runtime():
    store = MagicMock()
    store.async_save = AsyncMock()
    return RuntimeManager(store)


@pytest.fixture
def running():
    return {"fan": True}


@pytest.fixture
def manager(mock_hass, mock_hub, runtime, running):
    mock_hass.async_create_task = MagicMock(side_effect=lambda coro, name=None: coro.close())
    return DelayedOffManager(
        mock_hass, lambda: {"fan_auto_off_delay": 15}, mock_hub, runtime, lambda: running["fan"]
    )


@pytest.fixture
def timers():
    """Replace async_call_later; returns the list of (seconds, callback, cancel mock)."""
    calls = []

    def fake(hass, delay, action):
        cancel = MagicMock()
        calls.append((delay, action, cancel))
        return cancel

    with patch("custom_components.thermex_api.delayed_off.async_call_later", side_effect=fake):
        yield calls


@pytest.mark.asyncio
async def test_start_saves_the_due_time_and_arms_the_timers(manager, runtime, timers):
    await manager.async_start()

    assert manager.active and manager.remaining == 15
    assert manager.delay_minutes == 15
    assert runtime.get_delayed_off() == manager.scheduled_time
    runtime._store.async_save.assert_awaited()
    assert timers[0][0] == pytest.approx(15 * 60, abs=2)  # turn-off
    assert timers[1][0] == 60  # countdown


@pytest.mark.asyncio
async def test_start_needs_a_running_fan(manager, running, timers):
    running["fan"] = False

    with pytest.raises(ServiceValidationError) as exc:
        await manager.async_start()

    assert exc.value.translation_key == "fan_not_running"
    assert timers == []


@pytest.mark.asyncio
async def test_delay_is_kept_within_the_allowed_range(mock_hass, mock_hub, runtime):
    low = DelayedOffManager(mock_hass, lambda: {"fan_auto_off_delay": 0}, mock_hub, runtime, lambda: True)
    high = DelayedOffManager(mock_hass, lambda: {"fan_auto_off_delay": 999}, mock_hub, runtime, lambda: True)

    assert (low.delay_minutes, high.delay_minutes) == (1, 120)


@pytest.mark.asyncio
async def test_restart_stops_the_old_timers(manager, timers):
    await manager.async_start()
    await manager.async_start()

    old_off, old_count = timers[0][2], timers[1][2]
    old_off.assert_called_once()
    old_count.assert_called_once()


@pytest.mark.asyncio
async def test_cancel_clears_state_and_the_saved_timer(manager, runtime, timers):
    await manager.async_start()
    await manager.async_cancel()

    assert not manager.active and manager.remaining == 0 and manager.scheduled_time is None
    assert runtime.get_delayed_off() is None
    assert all(cancel.called for _, _, cancel in timers)


@pytest.mark.asyncio
async def test_cancel_without_a_timer_writes_nothing(manager, runtime):
    await manager.async_cancel()

    runtime._store.async_save.assert_not_awaited()


@pytest.mark.asyncio
async def test_shutdown_stops_timers_but_keeps_the_saved_timer(manager, runtime, timers):
    await manager.async_start()
    manager.shutdown()

    assert all(cancel.called for _, _, cancel in timers)
    assert runtime.get_delayed_off() is not None


@pytest.mark.asyncio
async def test_pending_timer_is_resumed_after_a_reload(manager, runtime, timers):
    runtime.set_delayed_off(dt_util.now() + timedelta(minutes=5))

    manager.restore()

    assert manager.active and manager.remaining == 5
    assert 290 <= timers[0][0] <= 300


@pytest.mark.asyncio
async def test_timer_that_came_due_while_down_is_dropped(manager, runtime, timers):
    runtime.set_delayed_off(dt_util.now() - timedelta(minutes=5))

    manager.restore()

    assert not manager.active
    assert runtime.get_delayed_off() is None
    assert timers == []


@pytest.mark.asyncio
async def test_countdown_ticks_down_and_reschedules(manager, timers):
    await manager.async_start()
    listener = MagicMock()
    manager.async_add_listener(listener)

    manager._tick()

    assert manager.remaining == 14
    listener.assert_called_once()
    assert len(timers) == 3  # turn-off, countdown, next countdown


@pytest.mark.asyncio
async def test_countdown_does_nothing_when_cancelled(manager):
    manager._tick()

    assert manager.remaining == 0


@pytest.mark.asyncio
async def test_when_due_the_fan_is_turned_off_and_the_timer_cleared(manager, mock_hub, runtime, timers):
    await manager.async_start()

    await manager._due(dt_util.now())

    mock_hub.send_update.assert_awaited_once_with({"Fan": {"fanonoff": 0, "fanspeed": 0}})
    assert not manager.active
    assert runtime.get_delayed_off() is None


@pytest.mark.asyncio
async def test_a_failed_turn_off_is_logged_not_raised(manager, mock_hub, timers, caplog):
    mock_hub.send_update = AsyncMock(side_effect=HomeAssistantError("offline"))
    await manager.async_start()

    await manager._due(dt_util.now())

    assert "Delayed turn-off failed" in caplog.text


@pytest.mark.asyncio
async def test_cancel_soon_only_acts_on_an_active_timer(manager, mock_hass, timers):
    manager.cancel_soon()
    mock_hass.async_create_task.assert_not_called()

    await manager.async_start()
    manager.cancel_soon()
    mock_hass.async_create_task.assert_called_once()


@pytest.mark.asyncio
async def test_listeners_can_unsubscribe(manager, timers):
    listener = MagicMock()
    remove = manager.async_add_listener(listener)
    remove()
    remove()  # harmless twice

    await manager.async_start()

    listener.assert_not_called()
