# File: custom_components/thermex_api/button.py

import logging

from homeassistant.components.button import ButtonEntity
from homeassistant.const import EntityCategory

from .coordinator import ThermexCoordinator
from .data import ThermexConfigEntry
from .entity import ThermexEntity

_LOGGER = logging.getLogger(__name__)

PARALLEL_UPDATES = 1


async def async_setup_entry(hass, entry: ThermexConfigEntry, async_add_entities) -> None:
    """Set up the buttons for Thermex API."""
    coordinator = entry.runtime_data.coordinator
    async_add_entities([
        ResetRuntimeButton(coordinator),
        DelayedTurnOffButton(coordinator),
    ])


class ResetRuntimeButton(ThermexEntity, ButtonEntity):
    """Button that resets the fan runtime (filter usage) counter."""

    _attr_entity_category = EntityCategory.CONFIG  # maintenance of the filter counter
    _attr_translation_key = "thermex_button_reset_runtime"
    _requires_connection = False  # only resets the locally stored counter

    def __init__(self, coordinator: ThermexCoordinator):
        super().__init__(coordinator)
        self._attr_unique_id = f"{self._hub.unique_id}_reset_runtime"

    async def async_press(self) -> None:
        """Handle the button press: reset runtime and filter time."""
        await self.coordinator.async_reset_runtime()


class DelayedTurnOffButton(ThermexEntity, ButtonEntity):
    """Button that starts delayed turn-off for the fan."""

    _attr_translation_key = "thermex_button_delayed_turn_off"

    def __init__(self, coordinator: ThermexCoordinator):
        super().__init__(coordinator)
        self._attr_unique_id = f"{self._hub.unique_id}_delayed_turn_off"

    async def async_press(self) -> None:
        """Handle the button press: start delayed turn-off (errors reach the user)."""
        await self.coordinator.delayed_off.async_start()
