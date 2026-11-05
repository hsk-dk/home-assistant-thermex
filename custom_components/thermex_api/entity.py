"""Shared base entity for the Thermex integration."""
from typing import Any

from homeassistant.core import callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import DeviceInfo, Entity

from .hub import ThermexHub


class ThermexEntity(Entity):
    """Base class: device info, per-hood notifications and availability."""

    _attr_has_entity_name = True
    _attr_should_poll = False
    # Entities that only use locally stored data (filter counters, ...) stay
    # available while the hood is offline.
    _requires_connection = True

    def __init__(self, hub: ThermexHub) -> None:
        self._hub = hub

    @property
    def device_info(self) -> DeviceInfo:
        return self._hub.device_info

    @property
    def available(self) -> bool:
        return not self._requires_connection or self._hub.available

    async def async_added_to_hass(self) -> None:
        """Subscribe to this hood's notifications and availability changes."""
        await super().async_added_to_hass()
        self.async_on_remove(
            async_dispatcher_connect(self.hass, self._hub.signal, self._handle_notify)
        )
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass, self._hub.availability_signal, self._handle_availability
            )
        )

    @callback
    def _handle_availability(self) -> None:
        """The hood went offline or came back."""
        self.async_write_ha_state()

    @callback
    def _handle_notify(self, ntf_type: str, data: dict[str, Any]) -> None:
        """Handle a notification from the hood (override in subclasses)."""
