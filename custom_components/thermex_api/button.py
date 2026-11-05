# File: custom_components/thermex_api/button.py

import logging

from homeassistant.components.button import ButtonEntity
from homeassistant.const import EntityCategory
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.dispatcher import async_dispatcher_send

from .const import DOMAIN
from .data import ThermexConfigEntry
from .entity import ThermexEntity
from .entity_lookup import find_fan_entity_id
from .hub import ThermexHub
from .runtime_manager import RuntimeManager

_LOGGER = logging.getLogger(__name__)

PARALLEL_UPDATES = 1

async def async_setup_entry(hass, entry: ThermexConfigEntry, async_add_entities) -> None:
    """Set up the Reset Runtime button for Thermex API."""
    hub = entry.runtime_data.hub
    runtime_manager = entry.runtime_data.runtime_manager
    async_add_entities([
        ResetRuntimeButton(hub, runtime_manager, entry.entry_id),
        DelayedTurnOffButton(hub, entry.entry_id),
    ])


class ResetRuntimeButton(ThermexEntity, ButtonEntity):
    """Button that resets the fan runtime (filter usage) counter."""

    _attr_entity_category = EntityCategory.CONFIG  # maintenance of the filter counter
    _requires_connection = False  # only resets the locally stored counter

    def __init__(self, hub: ThermexHub, runtime_manager: RuntimeManager, entry_id: str):
        super().__init__(hub)
        self._runtime_manager = runtime_manager
        self._entry_id = entry_id

        self._attr_unique_id = f"{hub.unique_id}_reset_runtime"
        self._attr_translation_key = "thermex_button_reset_runtime"

    async def async_press(self) -> None:
        """Handle the button press: reset runtime and filter time."""
        if self._runtime_manager is None:
            _LOGGER.error("Runtime manager is not initialized!")
            return
        self._runtime_manager.reset()
        await self._runtime_manager.save()

        # Trigger fan + filter sensor updates
        async_dispatcher_send(
            self.hass,
            self._hub.signal,
            "fan",
            {"Fan": {}},
        )


class DelayedTurnOffButton(ThermexEntity, ButtonEntity):
    """Button that starts delayed turn-off for the fan."""

    def __init__(self, hub: ThermexHub, entry_id: str):
        super().__init__(hub)
        self._entry_id = entry_id

        self._attr_unique_id = f"{hub.unique_id}_delayed_turn_off"
        self._attr_translation_key = "thermex_button_delayed_turn_off"

    async def async_press(self) -> None:
        """Handle the button press: start delayed turn-off for the fan."""
        fan_entity_id = find_fan_entity_id(self.hass, self._hub.unique_id)
        if not fan_entity_id:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="fan_entity_not_found",
            )

        # blocking, so a ServiceValidationError (fan not running) reaches the user
        await self.hass.services.async_call(
            DOMAIN,
            "start_delayed_off",
            {"entity_id": fan_entity_id},
            blocking=True,
        )
