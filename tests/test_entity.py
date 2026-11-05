"""Tests for the shared ThermexEntity base."""
from unittest.mock import MagicMock, patch

import pytest

from custom_components.thermex_api.entity import ThermexEntity


class _Local(ThermexEntity):
    _requires_connection = False


@pytest.fixture
def hub(mock_hub):
    mock_hub.available = True
    return mock_hub


def test_unavailable_when_hood_offline(hub):
    entity = ThermexEntity(hub)
    hub.available = False

    assert entity.available is False


def test_local_entities_stay_available(hub):
    entity = _Local(hub)
    hub.available = False

    assert entity.available is True


def test_device_info_comes_from_hub(hub):
    assert ThermexEntity(hub).device_info == hub.device_info


@pytest.mark.asyncio
async def test_subscribes_to_this_hoods_signals_and_cleans_up(hub, mock_hass):
    entity = ThermexEntity(hub)
    entity.hass = mock_hass
    entity.async_on_remove = MagicMock()

    with patch("custom_components.thermex_api.entity.async_dispatcher_connect") as connect:
        await entity.async_added_to_hass()

    signals = [c.args[1] for c in connect.call_args_list]
    assert signals == [hub.signal, hub.availability_signal]
    assert entity.async_on_remove.call_count == 2  # unsubscribed automatically on removal


def test_availability_change_writes_state(hub):
    entity = ThermexEntity(hub)
    entity.async_write_ha_state = MagicMock()

    entity._handle_availability()

    entity.async_write_ha_state.assert_called_once()
