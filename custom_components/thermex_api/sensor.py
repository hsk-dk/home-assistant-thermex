# File: custom_components/thermex_api/sensor.py
"""
Thermex API sensors:
 - filter runtime (hours)
 - last reset of the runtime counter
 - connection status (diagnostic)
 - scheduled delayed turn-off
"""
import logging
from datetime import datetime
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.const import EntityCategory, UnitOfTime
from homeassistant.core import callback
from homeassistant.helpers.event import async_call_later
from homeassistant.util.dt import parse_datetime

from .const import RUNTIME_UPDATE_INTERVAL
from .coordinator import ThermexCoordinator
from .data import ThermexConfigEntry
from .entity import ThermexEntity

_LOGGER = logging.getLogger(__name__)

PARALLEL_UPDATES = 0

CONNECTION_STATES = ["connected", "disconnected", "error", "closed"]


async def async_setup_entry(hass, entry: ThermexConfigEntry, async_add_entities):
    """Set up the Thermex sensors."""
    coordinator = entry.runtime_data.coordinator

    async_add_entities([
        LastResetSensor(coordinator),
        RuntimeHoursSensor(coordinator),
        ConnectionStatusSensor(coordinator),
        DelayedTurnOffSensor(coordinator),
    ])


class RuntimeHoursSensor(ThermexEntity, SensorEntity):
    """Sensor for the cumulative runtime hours of the Thermex fan."""

    _attr_device_class = SensorDeviceClass.DURATION
    _attr_native_unit_of_measurement = UnitOfTime.HOURS
    _attr_state_class = SensorStateClass.TOTAL_INCREASING  # a drop = the filter was reset
    _attr_suggested_display_precision = 1
    _attr_translation_key = "thermex_sensor_runtime_hours"

    def __init__(self, coordinator: ThermexCoordinator):
        super().__init__(coordinator)
        self._runtime_manager = coordinator.runtime_manager
        self._attr_unique_id = f"{self._hub.unique_id}_runtime_hours"
        self._update_timer = None

    async def async_will_remove_from_hass(self):
        """Clean up when removing sensor."""
        await super().async_will_remove_from_hass()
        self._stop_timer()

    @callback
    def _handle_coordinator_update(self) -> None:
        """While the fan runs, the counter grows between two updates from the hood."""
        if self.coordinator.fan_running:
            if self._update_timer is None:
                self._schedule_update()
        else:
            self._stop_timer()
        super()._handle_coordinator_update()

    def _stop_timer(self) -> None:
        if self._update_timer:
            self._update_timer()
            self._update_timer = None

    def _schedule_update(self) -> None:
        self._update_timer = async_call_later(
            self.hass, RUNTIME_UPDATE_INTERVAL, self._periodic_update
        )

    @callback
    def _periodic_update(self, _now: datetime) -> None:
        """Show the time that has passed since the last update."""
        self._update_timer = None
        self.async_write_ha_state()
        if self.coordinator.fan_running:
            self._schedule_update()

    @property
    def native_value(self):
        return self._runtime_manager.get_runtime_hours()


class LastResetSensor(ThermexEntity, SensorEntity):
    """Timestamp when the runtime counter was last reset."""

    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_translation_key = "thermex_sensor_last_reset"
    _requires_connection = False  # stored locally

    def __init__(self, coordinator: ThermexCoordinator):
        super().__init__(coordinator)
        self._runtime_manager = coordinator.runtime_manager
        self._attr_unique_id = f"{self._hub.unique_id}_last_reset"

    @property
    def native_value(self):
        iso = self._runtime_manager.get_last_reset()
        if iso:
            return parse_datetime(iso)
        return None


class ConnectionStatusSensor(ThermexEntity, SensorEntity):
    """Connection state of the hood (diagnostic)."""

    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = CONNECTION_STATES
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_entity_registry_enabled_default = False
    _attr_translation_key = "thermex_sensor_connection_status"
    _requires_connection = False  # it exists to show that the hood is offline

    def __init__(self, coordinator: ThermexCoordinator):
        super().__init__(coordinator)
        self._attr_unique_id = f"{self._hub.unique_id}_connection_status"

    @property
    def native_value(self):
        """Return the connection state."""
        state = self._hub.connection_state
        return state if state in CONNECTION_STATES else "disconnected"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Only slowly changing details."""
        return {
            "last_error": self._hub.last_error,
            "protocol_version": self._hub.protocol_version,
        }


class DelayedTurnOffSensor(ThermexEntity, SensorEntity):
    """Sensor that shows the scheduled turn-off time for the fan."""

    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_translation_key = "thermex_sensor_delayed_turn_off"

    def __init__(self, coordinator: ThermexCoordinator):
        super().__init__(coordinator)
        self._delayed_off = coordinator.delayed_off
        self._attr_unique_id = f"{self._hub.unique_id}_delayed_turn_off_time"

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(self._delayed_off.async_add_listener(self.async_write_ha_state))

    @property
    def native_value(self):
        """Return the scheduled turn-off time."""
        return self._delayed_off.scheduled_time

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional delayed turn-off information."""
        return {
            "delayed_off_active": self._delayed_off.active,
            "delayed_off_remaining": self._delayed_off.remaining,
            "delayed_off_delay": self._delayed_off.delay_minutes,
        }
