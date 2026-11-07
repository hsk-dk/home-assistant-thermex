"""Tests for the filter alert binary sensor."""
from unittest.mock import MagicMock

import pytest
from homeassistant.components.binary_sensor import BinarySensorDeviceClass

from custom_components.thermex_api.binary_sensor import ThermexFilterAlert, async_setup_entry


@pytest.fixture
def alert(coordinator):
    # thresholds from the config entry: 100 hours / 90 days
    return ThermexFilterAlert(coordinator)


@pytest.mark.asyncio
async def test_setup(coordinator, mock_hass, mock_config_entry):
    mock_config_entry.runtime_data = MagicMock(coordinator=coordinator)
    add = MagicMock()

    await async_setup_entry(mock_hass, mock_config_entry, add)

    assert [type(e) for e in add.call_args.args[0]] == [ThermexFilterAlert]


def test_modelling(alert, mock_hub):
    mock_hub.available = False

    assert alert.device_class == BinarySensorDeviceClass.PROBLEM
    assert alert.unique_id == "test_thermex_hub_threshold_alert"
    assert alert.available is True  # computed from stored data


def test_off_below_both_thresholds(alert):
    assert alert.is_on is False


def test_on_when_the_hours_threshold_is_reached(alert, runtime_manager):
    runtime_manager.get_runtime_hours.return_value = 100

    assert alert.is_on is True
    assert alert.extra_state_attributes["hours_exceeded"] is True
    assert alert.extra_state_attributes["days_exceeded"] is False


def test_on_when_the_filter_is_too_old(alert, runtime_manager):
    runtime_manager.get_days_since_reset.return_value = 90

    assert alert.is_on is True
    assert alert.extra_state_attributes["days_exceeded"] is True
    assert alert.extra_state_attributes["hours_exceeded"] is False


def test_without_a_reset_date_a_little_use_does_not_alert(alert, runtime_manager):
    runtime_manager.get_days_since_reset.return_value = None
    runtime_manager.get_runtime_hours.return_value = 2

    assert alert.is_on is False


def test_without_a_reset_date_real_use_alerts(alert, runtime_manager):
    runtime_manager.get_days_since_reset.return_value = None
    runtime_manager.get_runtime_hours.return_value = 6

    assert alert.is_on is True


def test_attributes_use_none_for_unknown_values(alert, runtime_manager):
    runtime_manager.get_days_since_reset.return_value = None
    runtime_manager.get_last_reset.return_value = None

    attrs = alert.extra_state_attributes

    assert attrs["days_since_reset"] is None
    assert attrs["last_reset"] is None
    assert "trigger_reason" not in attrs


def test_attributes_show_the_thresholds(alert):
    attrs = alert.extra_state_attributes

    assert attrs["runtime_hours"] == 12.5
    assert attrs["hours_threshold"] == 100
    assert attrs["days_threshold"] == 90
    assert attrs["days_since_reset"] == 10


def test_thresholds_follow_the_options(alert, mock_config_entry):
    mock_config_entry.options = {**mock_config_entry.options, "fan_alert_hours": 10}

    assert alert.is_on is True  # 12.5 h >= 10 h
