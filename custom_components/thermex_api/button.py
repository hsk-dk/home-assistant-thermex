# File: custom_components/thermex_api/button.py

import logging
from homeassistant.components.button import ButtonEntity
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.storage import Store
from homeassistant.helpers.entity import DeviceInfo

from .const import DOMAIN, THERMEX_NOTIFY, STORAGE_VERSION, RUNTIME_STORAGE_FILE
from .hub import ThermexHub
from .runtime_manager import RuntimeManager

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass, entry, async_add_entities):
    """Set up the Reset Runtime button for Thermex API."""
    #hub: ThermexHub = hass.data[DOMAIN][entry.entry_id]
    entry_data = hass.data[DOMAIN][entry.entry_id]
    hub = entry_data["hub"]
    runtime_manager = entry_data["runtime_manager"]
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
 #       _LOGGER.info("Thermex runtime/filter time has been reset.")

        # Trigger fan + filter sensor updates
        async_dispatcher_send(
            self.hass,
            THERMEX_NOTIFY,
            "fan",
            {"Fan": {}},
        )

        # Coordinator refresh (per entry)
        entry_data = self.hass.data[DOMAIN].get(self._entry_id)
        coordinator = getattr(entry_data, "coordinator", None) if entry_data else None
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
        # Find the fan entity and start delayed turn-off
        entry_data = self.hass.data[DOMAIN].get(self._entry_id)
        if not entry_data:
            _LOGGER.error("Entry data not found for delayed turn-off")
            return

        # Get the fan entity
        fan_entity_id = f"fan.{self._hub.unique_id}_fan"
        fan_entity = None
        
        # Look for the fan entity in the entity registry
        for entity in self.hass.states.async_all():
            if entity.entity_id == fan_entity_id:
                # Get the actual entity object via entity registry
                entity_registry = self.hass.helpers.entity_registry.async_get(self.hass)
                entity_entry = entity_registry.async_get(entity.entity_id)
                if entity_entry and entity_entry.platform == DOMAIN:
                    # Call the fan service
                    await self.hass.services.async_call(
                        "fan",
                        "start_delayed_off",
                        {"entity_id": fan_entity_id},
                        blocking=True
                    )
                    return

        _LOGGER.error("Fan entity not found for delayed turn-off")
