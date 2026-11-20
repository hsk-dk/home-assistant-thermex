"""Tests for diagnostics."""
from unittest.mock import MagicMock

import pytest

from custom_components.thermex_api.diagnostics import async_get_config_entry_diagnostics
from custom_components.thermex_api.state import FanState, ThermexState


@pytest.mark.asyncio
async def test_diagnostics(mock_hass, mock_hub, mock_config_entry, runtime_manager, coordinator):
    mock_hub.diagnostics.return_value = {
        "host": "192.168.1.100",
        "unique_id": "thermex_abc",
        "connection_state": "connected",
        "websocket_connected": True,
        "pending_requests": ["status"],
        "protocol_version": "1.1",
        "last_error": None,
        "last_status": {"Response": "Status"},
        "recent_messages": ["a", "b"],
    }
    coordinator.data = ThermexState(fan=FanState(on=True, speed=2))
    runtime_manager.get_runtime_hours.return_value = 50.0
    runtime_manager.get_days_since_reset.return_value = 3
    mock_config_entry.runtime_data = MagicMock(
        hub=mock_hub, runtime_manager=runtime_manager, coordinator=coordinator
    )

    result = await async_get_config_entry_diagnostics(mock_hass, mock_config_entry)

    assert result["host"] == "**REDACTED**"
    assert result["unique_id"] == "**REDACTED**"
    assert result["connection_state"] == "connected"
    assert result["websocket_connected"] is True
    assert result["state"]["fan"] == {"on": True, "speed": 2}
    assert result["state"]["light"] is None
    assert result["runtime_data"] == {
        "runtime_hours": 50.0,
        "last_reset": "2026-01-15T10:00:00+00:00",
        "days_since_reset": 3,
    }
    assert "api_key" not in str(result)


@pytest.mark.asyncio
async def test_diagnostics_before_the_first_state(mock_hass, mock_hub, mock_config_entry, runtime_manager, coordinator):
    mock_hub.diagnostics.return_value = {"host": "h"}
    coordinator.data = None
    mock_config_entry.runtime_data = MagicMock(
        hub=mock_hub, runtime_manager=runtime_manager, coordinator=coordinator
    )

    result = await async_get_config_entry_diagnostics(mock_hass, mock_config_entry)

    assert result["state"] is None
