from homeassistant.helpers.entity import Entity
from typing import Any

class ThermexDiagnosticsSensor(Entity):
    def __init__(self, coordinator):
        self._coordinator = coordinator
        self._attr_name = "Thermex Diagnostics"
        self._attr_unique_id = "thermex_diagnostics"

    @property
    def state(self) -> str:
        # Example: "connected" or "disconnected"
        return "connected" if self._coordinator.api.is_connected else "disconnected"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        # Example: Expose error messages and other diagnostics
        return {
            "last_error": self._coordinator.api.last_error,
            "last_update": self._coordinator.last_update_success,
        }

    async def async_update(self):
        await self._coordinator.async_request_refresh()