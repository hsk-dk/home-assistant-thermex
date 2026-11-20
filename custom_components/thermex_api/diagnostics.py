"""Diagnostics support for Thermex integration."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.core import HomeAssistant

from .data import ThermexConfigEntry

TO_REDACT = {"host", "api_key", "unique_id"}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ThermexConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry (never the API password)."""
    data = entry.runtime_data
    runtime_manager = data.runtime_manager
    state = data.coordinator.data

    diagnostics = {
        **data.hub.diagnostics(),
        "state": asdict(state) if state else None,
        "runtime_data": {
            "runtime_hours": runtime_manager.get_runtime_hours(),
            "last_reset": runtime_manager.get_last_reset(),
            "days_since_reset": runtime_manager.get_days_since_reset(),
        },
    }
    return async_redact_data(diagnostics, TO_REDACT)
