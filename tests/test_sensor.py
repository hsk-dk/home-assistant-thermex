"""Tests for the sensors."""
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass
from homeassistant.const import EntityCategory, UnitOfTime

from custom_components.thermex_api.sensor import (
    ConnectionStatusSensor,
    DelayedTurnOffSensor,
    LastResetSensor,
    RuntimeHoursSensor,
    async_setup_entry,
)


@pytest.mark.asyncio
async def test_setup_adds_the_four_sensors(coordinator, mock_hass, mock_config_entry):
    mock_config_entry.runtime_data = MagicMock(coordinator=coordinator)
    add = MagicMock()

    await async_setup_entry(mock_hass, mock_config_entry, add)

    kinds = {type(e) for e in add.call_args.args[0]}
    assert kinds == {LastResetSensor, RuntimeHoursSensor, ConnectionStatusSensor, DelayedTurnOffSensor}


class TestRuntimeHoursSensor:
    @pytest.fixture
    def sensor(self, coordinator, mock_hass):
        entity = RuntimeHoursSensor(coordinator)
        entity.hass = mock_hass
        entity.async_write_ha_state = MagicMock()
        return entity

    def test_modelling(self, sensor):
        assert sensor.device_class == SensorDeviceClass.DURATION
        assert sensor.native_unit_of_measurement == UnitOfTime.HOURS
        assert sensor.state_class == SensorStateClass.TOTAL_INCREASING
        assert sensor.unique_id == "test_thermex_hub_runtime_hours"

    def test_value_is_the_stored_runtime(self, sensor):
        assert sensor.native_value == 12.5

    def test_starts_a_timer_when_the_fan_runs(self, sensor, coordinator):
        coordinator.fan_running = True

        with patch("custom_components.thermex_api.sensor.async_call_later") as later:
            sensor._handle_coordinator_update()
            sensor._handle_coordinator_update()  # no second timer

        later.assert_called_once()
        assert sensor.async_write_ha_state.call_count == 2

    def test_stops_the_timer_when_the_fan_stops(self, sensor, coordinator):
        cancel = MagicMock()
        sensor._update_timer = cancel
        coordinator.fan_running = False

        sensor._handle_coordinator_update()

        cancel.assert_called_once()
        assert sensor._update_timer is None

    def test_periodic_update_refreshes_and_reschedules_while_running(self, sensor, coordinator):
        coordinator.fan_running = True

        with patch("custom_components.thermex_api.sensor.async_call_later") as later:
            sensor._periodic_update(datetime.now(timezone.utc))

        sensor.async_write_ha_state.assert_called_once()
        later.assert_called_once()

    def test_periodic_update_stops_when_the_fan_has_stopped(self, sensor, coordinator):
        coordinator.fan_running = False

        with patch("custom_components.thermex_api.sensor.async_call_later") as later:
            sensor._periodic_update(datetime.now(timezone.utc))

        later.assert_not_called()

    @pytest.mark.asyncio
    async def test_removal_cancels_the_timer(self, sensor):
        cancel = MagicMock()
        sensor._update_timer = cancel

        await sensor.async_will_remove_from_hass()

        cancel.assert_called_once()


class TestLastResetSensor:
    @pytest.fixture
    def sensor(self, coordinator):
        return LastResetSensor(coordinator)

    def test_value_is_a_timestamp(self, sensor):
        assert sensor.native_value == datetime(2026, 1, 15, 10, 0, tzinfo=timezone.utc)

    def test_never_reset(self, sensor, runtime_manager):
        runtime_manager.get_last_reset.return_value = None

        assert sensor.native_value is None

    def test_is_a_local_diagnostic(self, sensor, mock_hub):
        mock_hub.available = False

        assert sensor.device_class == SensorDeviceClass.TIMESTAMP
        assert sensor.entity_category == EntityCategory.DIAGNOSTIC
        assert sensor.available is True  # stored locally


class TestConnectionStatusSensor:
    @pytest.fixture
    def sensor(self, coordinator):
        return ConnectionStatusSensor(coordinator)

    @pytest.mark.parametrize("state", ["connected", "disconnected", "error", "closed"])
    def test_states_follow_the_hub(self, sensor, mock_hub, state):
        mock_hub.connection_state = state

        assert sensor.native_value == state

    def test_unknown_state_is_reported_as_disconnected(self, sensor, mock_hub):
        mock_hub.connection_state = "something new"

        assert sensor.native_value == "disconnected"

    def test_attributes(self, sensor, mock_hub):
        mock_hub.last_error = "boom"

        assert sensor.extra_state_attributes == {"last_error": "boom", "protocol_version": "1.0"}

    def test_is_a_disabled_diagnostic_enum_that_stays_available(self, sensor, mock_hub):
        mock_hub.available = False

        assert sensor.device_class == SensorDeviceClass.ENUM
        assert sensor.entity_category == EntityCategory.DIAGNOSTIC
        assert sensor.entity_registry_enabled_default is False
        assert sensor.available is True


class TestDelayedTurnOffSensor:
    @pytest.fixture
    def sensor(self, coordinator, mock_hass):
        entity = DelayedTurnOffSensor(coordinator)
        entity.hass = mock_hass
        entity.async_write_ha_state = MagicMock()
        return entity

    def test_no_timer(self, sensor):
        assert sensor.native_value is None
        assert sensor.extra_state_attributes == {
            "delayed_off_active": False, "delayed_off_remaining": 0, "delayed_off_delay": 60,
        }

    def test_active_timer(self, sensor, delayed_off):
        when = datetime(2026, 11, 7, 12, 0, tzinfo=timezone.utc)
        delayed_off.active, delayed_off.remaining, delayed_off.scheduled_time = True, 5, when

        assert sensor.native_value == when
        assert sensor.extra_state_attributes["delayed_off_remaining"] == 5

    @pytest.mark.asyncio
    async def test_follows_the_timer(self, sensor, delayed_off):
        from custom_components.thermex_api.entity import ThermexEntity

        sensor.async_on_remove = MagicMock()
        with patch.object(ThermexEntity, "async_added_to_hass"):
            await sensor.async_added_to_hass()

        delayed_off.async_add_listener.assert_called_once_with(sensor.async_write_ha_state)
