# File: custom_components/thermex_api/button.py

import logging

from homeassistant.components.button import ButtonEntity
from homeassistant.helpers.dispatcher import async_dispatcher_send

from .const import DOMAIN, THERMEX_NOTIFY
from .entity_lookup import find_fan_entity_id
from .hub import ThermexHub
from .runtime_manager import RuntimeManager

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass, entry, async_add_entities) -> None:
    """Set up the Reset Runtime button for Thermex API."""
    entry_data = hass.data[DOMAIN][entry.entry_id]
    hub = entry_data.get("hub")
    runtime_manager = entry_data.get("runtime_manager")
    
    if not hub or not runtime_manager:
        _LOGGER.error("Missing hub or runtime_manager in entry data")
        return
    async_add_entities([
        ResetRuntimeButton(hub, runtime_manager, entry.entry_id),
        DelayedTurnOffButton(hub, entry.entry_id),
    ])


class ResetRuntimeButton(ButtonEntity):
    """Button that resets the fan runtime (filter usage) counter."""

    def __init__(self, hub: ThermexHub, runtime_manager: RuntimeManager, entry_id: str):
        self._hub = hub
        self._runtime_manager = runtime_manager
        self._entry_id = entry_id

        self._attr_unique_id = f"{hub.unique_id}_reset_runtime"
        self._attr_translation_key = "thermex_button_reset_runtime"
        self._attr_has_entity_name = True
        self._attr_icon = "mdi:refresh"
        self._attr_device_info = hub.device_info

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
            THERMEX_NOTIFY,
            "fan",
            {"Fan": {}},
        )

        # Coordinator refresh (per entry)
        entry_data = self.hass.data[DOMAIN].get(self._entry_id)
        coordinator = entry_data.get("coordinator") if entry_data else None
        if coordinator:
            await coordinator.async_request_refresh()


class DelayedTurnOffButton(ButtonEntity):
    """Button that starts delayed turn-off for the fan."""

    def __init__(self, hub: ThermexHub, entry_id: str):
        self._hub = hub
        self._entry_id = entry_id

        self._attr_unique_id = f"{hub.unique_id}_delayed_turn_off"
        self._attr_translation_key = "thermex_button_delayed_turn_off"
        self._attr_has_entity_name = True
        self._attr_icon = "mdi:timer-off"
        self._attr_device_info = hub.device_info

    async def async_press(self) -> None:
        """Handle the button press: start delayed turn-off for the fan."""
        _LOGGER.info("DelayedTurnOffButton pressed")
        
        fan_entity_id = find_fan_entity_id(self.hass, self._hub.unique_id)
        if not fan_entity_id:
            _LOGGER.error("Could not find the Thermex fan entity in the entity registry")
            return

        await self.hass.services.async_call(
            DOMAIN,
            "start_delayed_off",
            {"entity_id": fan_entity_id},
            blocking=False,
        )
