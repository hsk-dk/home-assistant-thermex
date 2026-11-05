"""Tests for __init__ setup functions."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady

from custom_components.thermex_api import async_setup_entry, async_unload_entry
from custom_components.thermex_api.hub import ThermexAuthError


class TestInit:
    """Test __init__ functions."""

    @pytest.fixture
    def mock_integration(self):
        """Create a mock integration."""
        integration = MagicMock()
        integration.version = "1.0.0"
        return integration

    @pytest.fixture
    def mock_hub(self):
        hub = MagicMock()
        hub.connect = AsyncMock()
        hub.close = AsyncMock()
        return hub

    @pytest.fixture
    def mock_runtime_manager(self):
        rm = MagicMock()
        rm.load = AsyncMock()
        return rm

    @pytest.fixture
    def setup_patches(self, mock_integration, mock_hub, mock_runtime_manager):
        """Patch everything async_setup_entry builds."""
        with patch('custom_components.thermex_api.async_get_integration', return_value=mock_integration), \
             patch('custom_components.thermex_api.ThermexHub', return_value=mock_hub), \
             patch('custom_components.thermex_api.RuntimeManager', return_value=mock_runtime_manager), \
             patch('custom_components.thermex_api.Store'):
            yield

    @pytest.mark.asyncio
    async def test_async_setup_entry_success(
        self, mock_hass, mock_config_entry, setup_patches, mock_hub, mock_runtime_manager
    ):
        """Successful setup stores hub + runtime manager in entry.runtime_data."""
        mock_hass.config_entries.async_forward_entry_setups = AsyncMock()

        result = await async_setup_entry(mock_hass, mock_config_entry)

        assert result is True
        mock_hub.connect.assert_called_once()
        mock_runtime_manager.load.assert_called_once()
        assert mock_config_entry.runtime_data.hub is mock_hub
        assert mock_config_entry.runtime_data.runtime_manager is mock_runtime_manager
        assert mock_hub.runtime_manager is mock_runtime_manager
        mock_hass.config_entries.async_forward_entry_setups.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_async_setup_entry_connection_failure(
        self, mock_hass, mock_config_entry, setup_patches, mock_hub
    ):
        """Connection errors make the entry retry later."""
        mock_hub.connect = AsyncMock(side_effect=Exception("Connection failed"))

        with pytest.raises(ConfigEntryNotReady):
            await async_setup_entry(mock_hass, mock_config_entry)

    @pytest.mark.asyncio
    async def test_async_setup_entry_auth_failure_starts_reauth(
        self, mock_hass, mock_config_entry, setup_patches, mock_hub
    ):
        """A rejected password raises ConfigEntryAuthFailed (HA starts reauth)."""
        mock_hub.connect = AsyncMock(side_effect=ThermexAuthError("bad password"))

        with pytest.raises(ConfigEntryAuthFailed):
            await async_setup_entry(mock_hass, mock_config_entry)

    @pytest.mark.asyncio
    async def test_async_setup_entry_closes_hub_if_platform_setup_fails(
        self, mock_hass, mock_config_entry, setup_patches, mock_hub
    ):
        """Never leave the websocket open if setup aborts after connecting."""
        mock_hass.config_entries.async_forward_entry_setups = AsyncMock(
            side_effect=RuntimeError("platform exploded")
        )

        with pytest.raises(RuntimeError):
            await async_setup_entry(mock_hass, mock_config_entry)

        mock_hub.close.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_hub_auth_failure_callback_starts_reauth(
        self, mock_hass, mock_config_entry, setup_patches, mock_hub
    ):
        """If the hood rejects the password later, reauth is started for the entry."""
        mock_hass.config_entries.async_forward_entry_setups = AsyncMock()
        await async_setup_entry(mock_hass, mock_config_entry)

        mock_hub.on_auth_failure()

        mock_config_entry.async_start_reauth.assert_called_once_with(mock_hass)

    @pytest.mark.asyncio
    async def test_async_unload_entry_success(self, mock_hass, mock_config_entry, mock_hub):
        """Unloading closes the hub connection."""
        mock_config_entry.runtime_data = MagicMock(hub=mock_hub)

        with patch.object(mock_hass.config_entries, 'async_unload_platforms', new_callable=AsyncMock, return_value=True):
            result = await async_unload_entry(mock_hass, mock_config_entry)

        assert result is True
        mock_hub.close.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_async_unload_entry_failure_keeps_hub(self, mock_hass, mock_config_entry, mock_hub):
        """A failed platform unload must not close the hub."""
        mock_config_entry.runtime_data = MagicMock(hub=mock_hub)

        with patch.object(mock_hass.config_entries, 'async_unload_platforms', new_callable=AsyncMock, return_value=False):
            result = await async_unload_entry(mock_hass, mock_config_entry)

        assert result is False
        mock_hub.close.assert_not_called()
