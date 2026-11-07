# File: binary_sensor.py
"""
Thermex API binary sensor for filter-life runtime alert.
"""
import logging
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)

from .const import MINIMUM_RUNTIME_FOR_NO_RESET_ALERT
from .coordinator import ThermexCoordinator
from .data import ThermexConfigEntry
from .entity import ThermexEntity

_LOGGER = logging.getLogger(__name__)

PARALLEL_UPDATES = 0


async def async_setup_entry(hass, entry: ThermexConfigEntry, async_add_entities):
    """Set up the Thermex filter-alert binary sensor."""
    async_add_entities([ThermexFilterAlert(entry.runtime_data.coordinator)])


class ThermexFilterAlert(ThermexEntity, BinarySensorEntity):
    """Binary sensor that goes ON when runtime or age of the filter exceeds its threshold."""

    _attr_device_class = BinarySensorDeviceClass.PROBLEM
    _attr_translation_key = "thermex_binary_sensor_threshold_alert"
    _requires_connection = False  # computed from locally stored runtime

    def __init__(self, coordinator: ThermexCoordinator):
        super().__init__(coordinator)
        self._runtime_manager = coordinator.runtime_manager
        self._attr_unique_id = f"{self._hub.unique_id}_threshold_alert"

    def _evaluate(self) -> dict[str, Any]:
        """Compare the runtime and the age of the filter with the thresholds."""
        options = self.coordinator.config_entry.options
        runtime_hours = self._runtime_manager.get_runtime_hours()
        days_since_reset = self._runtime_manager.get_days_since_reset()
        hours_threshold = options.get("fan_alert_hours", 30)
        days_threshold = options.get("fan_alert_days", 90)

        if days_since_reset is not None:
            days_exceeded = days_since_reset >= days_threshold
        else:
            # No reset date recorded: only alert after some real use, so a new
            # installation without any usage does not raise a false alarm
            days_exceeded = runtime_hours > MINIMUM_RUNTIME_FOR_NO_RESET_ALERT

        return {
            "runtime_hours": runtime_hours,
            "days_since_reset": days_since_reset,
            "hours_threshold": hours_threshold,
            "days_threshold": days_threshold,
            "hours_exceeded": runtime_hours >= hours_threshold,
            "days_exceeded": days_exceeded,
            "last_reset": self._runtime_manager.get_last_reset(),
        }

    @property
    def is_on(self) -> bool:
        """Return True if filter alert should be triggered."""
        result = self._evaluate()
        return result["hours_exceeded"] or result["days_exceeded"]

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the thresholds and which of them is exceeded."""
        return self._evaluate()
