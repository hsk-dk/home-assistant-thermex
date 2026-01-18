"""Diagnostics support for Thermex integration."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.typing import ConfigType

from homeassistant.config_entries import ConfigEntry

from .const import DOMAIN
from .hub import ThermexHub

_LOGGER = logging.getLogger(__name__)

async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""

    try:
        # Get the ThermexHub instance using proper entry_data pattern
        entry_data = hass.data[DOMAIN].get(entry.entry_id)
        if not entry_data:
            return {"error": "Entry data not found"}
        
        hub: ThermexHub = entry_data.get("hub")
        if not hub:
            return {"error": "Hub not found in entry data"}

        # Gather diagnostic info with safe attribute access
        diagnostics: dict[str, Any] = {
            "host": getattr(hub, "_host", "unknown"),
            "unique_id": getattr(hub, "unique_id", None),
            "connection_state": getattr(hub, "_connection_state", "unknown"),
            "pending_requests": list(hub._pending.keys()) if hasattr(hub, "_pending") else [],
            "websocket_connected": bool(getattr(hub, "_ws", None) and not hub._ws.closed),
            "last_status": getattr(hub, "last_status", None),
            "has_session": bool(getattr(hub, "_session", None) is not None),
            "has_recv_task": bool(
                getattr(hub, "_recv_task", None) is not None 
                and not hub._recv_task.done()
            ),
            "protocol_version": getattr(hub, "_protocol_version", "unknown"),
            "startup_complete": getattr(hub, "_startup_complete", False),
        }

        # Optionally include additional debug info if available
        # But NEVER include sensitive info such as API keys
        if hasattr(hub, "last_error") and hub.last_error:
            diagnostics["last_error"] = hub.last_error

        # If you store recent messages or state in hub, include a sample (not the full history)
        if hasattr(hub, "recent_messages") and hub.recent_messages:
            diagnostics["recent_messages"] = list(hub.recent_messages)[-5:]
        
        # Include runtime manager data if available
        runtime_manager = entry_data.get("runtime_manager")
        if runtime_manager:
            diagnostics["runtime_data"] = {
                "runtime_hours": runtime_manager.get_runtime_hours(),
                "last_reset": runtime_manager.get_last_reset(),
                "days_since_reset": runtime_manager.get_days_since_reset(),
            }

        return diagnostics
    
    except Exception as err:
        _LOGGER.exception("Error generating diagnostics: %s", err)
        return {"error": f"Failed to generate diagnostics: {err}"}
