"""Tests for __init__ setup functions."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from homeassistant.exceptions import ConfigEntryNotReady

from custom_components.thermex_api import async_setup_entry, async_unload_entry, async_create_coordinator


class TestInit:
    """Test __init__ functions."""

    @pytest.fixture
    def mock_integration(self):
        """Create a mock integration."""
        integration = MagicMock()
        integration.version = "1.0.0"
        return integration

    @pytest.mark.asyncio
    async def test_async_setup_entry_success(self, mock_hass, mock_config_entry, mock_integration):
        """Test successful setup entry."""
        mock_hub = MagicMock()
        mock_hub.connect = AsyncMock()
        mock_hub.get_coordinator_data = MagicMock(return_value={})
        
        mock_runtime_manager = MagicMock()
        mock_runtime_manager.load = AsyncMock()
        
        with patch('custom_components.thermex_api.async_get_integration', return_value=mock_integration):
            with patch('custom_components.thermex_api.ThermexHub', return_value=mock_hub):
                with patch('custom_components.thermex_api.RuntimeManager', return_value=mock_runtime_manager):
                    with patch('custom_components.thermex_api.Store'):
                        with patch.object(mock_hass.config_entries, 'async_forward_entry_setups', new_callable=AsyncMock):
                            result = await async_setup_entry(mock_hass, mock_config_entry)
                            
                            assert result is True
                            mock_hub.connect.assert_called_once()
                            mock_runtime_manager.load.assert_called_once()

    @pytest.mark.asyncio
    async def test_async_setup_entry_connection_failure(self, mock_hass, mock_config_entry, mock_integration):
        """Test setup entry fails on connection error."""
        mock_hub = MagicMock()
        mock_hub.connect = AsyncMock(side_effect=Exception("Connection failed"))
        
        with patch('custom_components.thermex_api.async_get_integration', return_value=mock_integration):
            with patch('custom_components.thermex_api.ThermexHub', return_value=mock_hub):
                with pytest.raises(ConfigEntryNotReady):
                    await async_setup_entry(mock_hass, mock_config_entry)

    @pytest.mark.asyncio
    async def test_async_unload_entry_success(self, mock_hass, mock_config_entry):
        """Test successful unload entry."""
        mock_hub = MagicMock()
        
        mock_hass.data = {
            "thermex_api": {
                mock_config_entry.entry_id: {
                    "hub": mock_hub,
                }
            }
        }
        
        with patch.object(mock_hass.config_entries, 'async_unload_platforms', new_callable=AsyncMock, return_value=True):
            result = await async_unload_entry(mock_hass, mock_config_entry)
            
            assert result is True
            # Verify entry data was removed
            assert mock_config_entry.entry_id not in mock_hass.data["thermex_api"]

    @pytest.mark.asyncio
    async def test_async_create_coordinator(self, mock_hass):
        """Test coordinator creation."""
        mock_hub = MagicMock()
        mock_hub.get_coordinator_data = MagicMock(return_value={"test": "data"})
        
        coordinator = await async_create_coordinator(mock_hass, mock_hub)
        
        assert coordinator is not None
        assert coordinator.name == "thermex_coordinator"

    @pytest.mark.asyncio
    async def test_coordinator_update_method(self, mock_hass):
        """Test coordinator update method calls hub."""
        mock_hub = MagicMock()
        mock_hub.get_coordinator_data = MagicMock(return_value={"test": "data"})
        
        coordinator = await async_create_coordinator(mock_hass, mock_hub)
        
        # Manually call the update method
        data = await coordinator._async_update_data()
        
        assert data == {"test": "data"}
        mock_hub.get_coordinator_data.assert_called()
