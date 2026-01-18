"""Tests for diagnostics module."""
import pytest
from unittest.mock import MagicMock

from custom_components.thermex_api.diagnostics import (
    async_get_config_entry_diagnostics,
)


class TestDiagnostics:
    """Test diagnostics functionality."""

    @pytest.mark.asyncio
    async def test_diagnostics_success(self, mock_hass, mock_hub, mock_config_entry):
        """Test successful diagnostics retrieval."""
        mock_hub._host = "192.168.1.100"
        mock_hub._connection_state = "connected"
        mock_hub._pending = {"req1": MagicMock()}
        mock_hub._ws = MagicMock(closed=False)
        mock_hub.last_status = {"status": "ok"}
        mock_hub._session = MagicMock()
        
        mock_hass.data = {
            "thermex_api": {
                mock_config_entry.entry_id: {
                    "hub": mock_hub
                }
            }
        }
        
        result = await async_get_config_entry_diagnostics(
            mock_hass,
            mock_config_entry
        )
        
        assert result["host"] == "192.168.1.100"
        assert result["connection_state"] == "connected"
        assert "req1" in result["pending_requests"]
        assert result["websocket_connected"] is True
        assert result["last_status"] == {"status": "ok"}
        assert result["has_session"] is True

    @pytest.mark.asyncio
    async def test_diagnostics_no_entry_data(self, mock_hass, mock_config_entry):
        """Test diagnostics when entry data not found."""
        mock_hass.data = {"thermex_api": {}}
        
        result = await async_get_config_entry_diagnostics(
            mock_hass,
            mock_config_entry
        )
        
        assert "error" in result
        assert result["error"] == "Entry data not found"

    @pytest.mark.asyncio
    async def test_diagnostics_no_hub(self, mock_hass, mock_config_entry):
        """Test diagnostics when hub not found."""
        mock_hass.data = {
            "thermex_api": {
                mock_config_entry.entry_id: {
                    "runtime_manager": MagicMock()
                }
            }
        }
        
        result = await async_get_config_entry_diagnostics(
            mock_hass,
            mock_config_entry
        )
        
        assert "error" in result
        assert result["error"] == "Hub not found in entry data"

    @pytest.mark.asyncio
    async def test_diagnostics_with_minimal_hub(self, mock_hass, mock_config_entry):
        """Test diagnostics with minimal hub attributes."""
        mock_hub = MagicMock()
        # Only set minimal attributes
        mock_hub._host = "192.168.1.1"
        mock_hub.unique_id = "test_unique_id"
        
        mock_hass.data = {
            "thermex_api": {
                mock_config_entry.entry_id: {
                    "hub": mock_hub
                }
            }
        }
        
        result = await async_get_config_entry_diagnostics(
            mock_hass,
            mock_config_entry
        )
        
        assert result["host"] == "192.168.1.1"
        assert result["unique_id"] == "test_unique_id"

    @pytest.mark.asyncio
    async def test_diagnostics_with_runtime_manager(self, mock_hass, mock_config_entry):
        """Test diagnostics includes runtime manager data."""
        mock_hub = MagicMock()
        mock_hub._host = "192.168.1.100"
        mock_hub.unique_id = "test_id"
        mock_hub.last_status = {"status": "ok"}
        mock_hub.last_error = None
        mock_hub.recent_messages = ["msg1", "msg2"]
        
        mock_runtime = MagicMock()
        mock_runtime.get_runtime_hours.return_value = 50.0
        mock_runtime.get_last_reset.return_value = "2026-01-15T10:00:00Z"
        mock_runtime.get_days_since_reset.return_value = 3
        
        mock_hass.data = {
            "thermex_api": {
                mock_config_entry.entry_id: {
                    "hub": mock_hub,
                    "runtime_manager": mock_runtime,
                }
            }
        }
        
        result = await async_get_config_entry_diagnostics(mock_hass, mock_config_entry)
        
        assert "runtime_data" in result
        assert result["runtime_data"]["runtime_hours"] == 50.0
        assert result["runtime_data"]["last_reset"] == "2026-01-15T10:00:00Z"
        assert result["runtime_data"]["days_since_reset"] == 3

    @pytest.mark.asyncio
    async def test_diagnostics_error_handling(self, mock_hass, mock_config_entry):
        """Test diagnostics handles errors gracefully."""
        mock_hass.data = {
            "thermex_api": {
                mock_config_entry.entry_id: None
            }
        }
        
        result = await async_get_config_entry_diagnostics(mock_hass, mock_config_entry)
        
        assert "error" in result
