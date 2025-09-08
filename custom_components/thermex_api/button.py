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
        _LOGGER.info("DelayedTurnOffButton pressed")
        
        try:
            # Try the new domain service first
            _LOGGER.info("Calling start_delayed_off_domain service")
            
            await self.hass.services.async_call(
                DOMAIN,
                "start_delayed_off_domain",
                {},  # No entity_id needed for domain service
                blocking=False
            )
            _LOGGER.info("Domain service call completed")
            
        except Exception as err:
            _LOGGER.error("Domain service failed, trying entity service: %s", err)
            
            try:
                # Fallback to entity service
                entity_id = f"fan.{self._hub.unique_id}_fan"
                _LOGGER.info("Calling start_delayed_off entity service for: %s", entity_id)
                
                await self.hass.services.async_call(
                    DOMAIN,
                    "start_delayed_off",
                    {"entity_id": entity_id},
                    blocking=False
                )
                _LOGGER.info("Entity service call completed")
                
            except Exception as err2:
                _LOGGER.error("Both service calls failed: %s", err2)
                import traceback
                _LOGGER.error("Traceback: %s", traceback.format_exc())
