"""Tests for the shared ThermexEntity base."""
from unittest.mock import MagicMock, patch

import pytest

from custom_components.thermex_api.entity import ThermexEntity


class _Local(ThermexEntity):
    _requires_connection = False


def test_unavailable_when_hood_offline(coordinator, mock_hub):
    mock_hub.available = False

    assert ThermexEntity(coordinator).available is False


def test_local_entities_stay_available(coordinator, mock_hub):
    mock_hub.available = False

    assert _Local(coordinator).available is True


def test_available_when_connected(coordinator):
    assert ThermexEntity(coordinator).available is True


def test_device_info_comes_from_hub(coordinator, mock_hub):
    assert ThermexEntity(coordinator).device_info == mock_hub.device_info


def test_entities_are_never_polled(coordinator):
    assert ThermexEntity(coordinator).should_poll is False


@pytest.mark.asyncio
async def test_follows_the_coordinator_and_the_hoods_availability(coordinator, mock_hub, mock_hass):
    entity = ThermexEntity(coordinator)
    entity.hass = mock_hass
    entity.async_on_remove = MagicMock()

    with patch("custom_components.thermex_api.entity.async_dispatcher_connect") as connect:
        await entity.async_added_to_hass()

    coordinator.async_add_listener.assert_called_once()  # the shared state
    assert connect.call_args.args[1] == mock_hub.availability_signal
    assert entity.async_on_remove.call_count == 2  # both unsubscribed on removal


def test_availability_change_writes_state(coordinator):
    entity = ThermexEntity(coordinator)
    entity.async_write_ha_state = MagicMock()

    entity._handle_availability()

    entity.async_write_ha_state.assert_called_once()
