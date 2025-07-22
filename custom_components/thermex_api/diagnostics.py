"""Diagnostics support for Thermex integration."""

from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry

from .hub import ThermexHub

async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""

    # Get the ThermexHub instance for this config entry
    hub: ThermexHub = hass.data["thermex_api"][entry.entry_id]

    # Gather diagnostic info
    diagnostics: dict[str, Any] = {
        "host": hub._host,
        "unique_id": getattr(hub, "unique_id", None),
        "connection_state": getattr(hub, "_connection_state", "unknown"),
        "pending_requests": list(hub._pending.keys()),
        "websocket_connected": bool(getattr(hub, "_ws", None) and not hub._ws.closed),
        "last_status": getattr(hub, "last_status", None),
        "has_session": bool(hub._session is not None),
        "has_recv_task": bool(hub._recv_task is not None and not hub._recv_task.done()),
    }

    # Optionally include additional debug info if available
    # But NEVER include sensitive info such as API keys
    # For example, recent errors, logs, protocol version, etc.
    if hasattr(hub, "last_error"):
        diagnostics["last_error"] = hub.last_error

    # If you store recent messages or state in hub, include a sample (not the full history)
    if hasattr(hub, "recent_messages"):
        diagnostics["recent_messages"] = list(hub.recent_messages)[-5:]

    return diagnostics