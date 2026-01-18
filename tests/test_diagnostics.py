"""Tests for diagnostics."""
import pytest
from unittest.mock import MagicMock, AsyncMock

from custom_components.thermex_api.diagnostics import async_get_config_entry_diagnostics


class TestDiagnostics:
    """Test diagnostics functionality."""

    @pytest.mark.asyncio
    async def test_diagnostics_basic(self, mock_hass, mock_hub, mock_config_entry):
        """Test basic diagnostics data."""
        mock_hass.data = {
            "thermex_api": {
                mock_config_entry.entry_id: {
                    "hub": mock_hub,
                }
            }
        }
        
        diagnostics = await async_get_config_entry_diagnostics(mock_hass, mock_config_entry)
        
        assert "integration_version" in diagnostics
        assert "device_info" in diagnostics
        assert "connection_state" in diagnostics

    @pytest.mark.asyncio
    async def test_diagnostics_includes_coordinator_data(self, mock_hass, mock_hub, mock_config_entry):
        """Test diagnostics includes coordinator data."""
        mock_hub.coordinator_data = {"Fan": {"fanonoff": 1}}
        mock_hass.data = {
            "thermex_api": {
                mock_config_entry.entry_id: {
                    "hub": mock_hub,
                }
            }
        }
        
        diagnostics = await async_get_config_entry_diagnostics(mock_hass, mock_config_entry)
        
        assert "coordinator_data" in diagnostics
        assert diagnostics["coordinator_data"]["Fan"]["fanonoff"] == 1

    @pytest.mark.asyncio
    async def test_diagnostics_safe_on_errors(self, mock_hass, mock_hub, mock_config_entry):
        """Test diagnostics handles errors safely."""
        mock_hub.device_info = None  # Simulate missing data
        mock_hass.data = {
            "thermex_api": {
                mock_config_entry.entry_id: {
                    "hub": mock_hub,
                }
            }
        }
        
        # Should not raise exception
        diagnostics = await async_get_config_entry_diagnostics(mock_hass, mock_config_entry)
        
        assert isinstance(diagnostics, dict)
