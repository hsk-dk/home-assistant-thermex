"""Thermex Fan entity with discrete presets and runtime attributes."""
import logging
from typing import Any

from homeassistant.components.fan import FanEntity, FanEntityFeature
from homeassistant.core import callback
from homeassistant.util.percentage import (
    ordered_list_item_to_percentage,
    percentage_to_ordered_list_item,
)

from .coordinator import ThermexCoordinator
from .data import ThermexConfigEntry
from .entity import ThermexEntity
from .state import PRESET_BY_SPEED, PRESET_MODES, SPEED_BY_PRESET, FanState

_LOGGER = logging.getLogger(__name__)

PARALLEL_UPDATES = 1


async def async_setup_entry(hass, entry: ThermexConfigEntry, async_add_entities) -> None:
    """Set up the Thermex fan."""
    async_add_entities([ThermexFan(entry.runtime_data.coordinator)])


class ThermexFan(ThermexEntity, FanEntity):
    """Thermex extractor fan with presets and runtime attributes.

    The four levels are both the presets and the speeds (25/50/75/100 %): the
    presets are kept on purpose so existing automations and the familiar names
    keep working.
    """

    _attr_supported_features = (
        FanEntityFeature.PRESET_MODE
        | FanEntityFeature.TURN_ON
        | FanEntityFeature.TURN_OFF
        | FanEntityFeature.SET_SPEED  # Enable percentage control
    )
    _attr_preset_modes = PRESET_MODES
    _attr_speed_count = 4  # 4 speeds: low(25%), medium(50%), high(75%), boost(100%)
    _attr_translation_key = "thermex_fan"
    _attr_name = None  # main entity: named after the device
    # Slow or noisy values: keep them in the state but out of the recorder
    _unrecorded_attributes = frozenset({
        "runtime_hours", "filter_time", "last_reset", "threshold", "alert",
        "delayed_off_remaining", "delayed_off_scheduled_time",
    })

    def __init__(self, coordinator: ThermexCoordinator) -> None:
        super().__init__(coordinator)
        self._runtime_manager = coordinator.runtime_manager
        self._delayed_off = coordinator.delayed_off
        self._attr_unique_id = f"{self._hub.unique_id}_fan"
        # What "turn on" without arguments switches to (the last level in use)
        last = self._runtime_manager.get_last_preset()
        self._last_active_preset = last if last in PRESET_MODES else "medium"

    @property
    def _fan(self) -> FanState | None:
        return self.coordinator.data.fan if self.coordinator.data else None

    @property
    def is_on(self) -> bool:
        return bool(self._fan and self._fan.running)

    @property
    def preset_mode(self) -> str | None:
        """The active level, or None when the fan is off."""
        if not self._fan or not self._fan.running:
            return None
        return PRESET_BY_SPEED.get(self._fan.speed)

    @property
    def percentage(self) -> int | None:
        """Return the current speed percentage (0 when off)."""
        if not self.is_on:
            return 0
        preset = self.preset_mode
        return ordered_list_item_to_percentage(PRESET_MODES, preset) if preset else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        options = self.coordinator.config_entry.options
        runtime_hours = self._runtime_manager.get_runtime_hours()
        threshold = options.get("fan_alert_hours", 30)
        attributes: dict[str, Any] = {
            "runtime_hours": runtime_hours,
            "filter_time": self._runtime_manager.get_filter_time(),
            "last_reset": self._runtime_manager.get_last_reset(),
            "threshold": threshold,
            "alert": runtime_hours >= threshold,
            "delayed_off_active": self._delayed_off.active,
            "delayed_off_remaining": self._delayed_off.remaining,
            "delayed_off_delay": self._delayed_off.delay_minutes,
        }
        if self._delayed_off.scheduled_time:
            attributes["delayed_off_scheduled_time"] = self._delayed_off.scheduled_time.isoformat()
        return attributes

    async def async_added_to_hass(self) -> None:
        """Follow the delayed turn-off timer as well as the hood."""
        await super().async_added_to_hass()
        self.async_on_remove(self._delayed_off.async_add_listener(self.async_write_ha_state))

    @callback
    def _handle_coordinator_update(self) -> None:
        if self.preset_mode:
            self._last_active_preset = self.preset_mode
        super()._handle_coordinator_update()

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        # The state comes from the Status read-back that send_update triggers: the
        # hood may clamp or rewrite what we sent.
        speed = SPEED_BY_PRESET[preset_mode]
        await self._hub.send_update({"Fan": {"fanonoff": int(speed > 0), "fanspeed": speed}})

    async def async_set_percentage(self, percentage: int) -> None:
        """Set the fan speed by percentage, mapping to the discrete levels."""
        if percentage == 0:
            await self.async_turn_off()
            return
        # 1-25% low, 26-50% medium, 51-75% high, 76-100% boost
        await self.async_set_preset_mode(percentage_to_ordered_list_item(PRESET_MODES, percentage))

    async def async_turn_on(self, percentage=None, preset_mode=None, **kwargs) -> None:
        if percentage is not None:
            await self.async_set_percentage(percentage)
        elif preset_mode:
            await self.async_set_preset_mode(preset_mode)
        else:
            await self.async_set_preset_mode(self._last_active_preset)

    async def async_turn_off(self, **kwargs) -> None:
        await self._delayed_off.async_cancel()
        await self.async_set_preset_mode("off")

    # Entity actions (see __init__.FAN_ACTIONS)

    async def async_reset(self, **kwargs) -> None:
        await self.coordinator.async_reset_runtime()

    async def start_delayed_off(self, minutes: int | None = None) -> None:
        await self._delayed_off.async_start(minutes)

    async def cancel_delayed_off(self) -> None:
        await self._delayed_off.async_cancel()
