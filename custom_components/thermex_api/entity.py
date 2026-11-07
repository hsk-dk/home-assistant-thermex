"""Shared base entity for the Thermex integration."""
from homeassistant.core import callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .coordinator import ThermexCoordinator


class ThermexEntity(CoordinatorEntity[ThermexCoordinator]):
    """Base class: device info, shared state and availability."""

    _attr_has_entity_name = True
    # Entities that only use locally stored data (filter counters, ...) stay
    # available while the hood is offline.
    _requires_connection = True

    def __init__(self, coordinator: ThermexCoordinator) -> None:
        super().__init__(coordinator)
        self._hub = coordinator.hub

    @property
    def device_info(self) -> DeviceInfo:
        return self._hub.device_info

    @property
    def available(self) -> bool:
        return not self._requires_connection or self._hub.available

    async def async_added_to_hass(self) -> None:
        """Follow the shared state, and the hood going offline or coming back."""
        await super().async_added_to_hass()
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass, self._hub.availability_signal, self._handle_availability
            )
        )

    @callback
    def _handle_availability(self) -> None:
        """The hood went offline or came back."""
        self.async_write_ha_state()
