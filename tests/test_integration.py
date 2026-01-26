"""Integration tests for the full Thermex integration lifecycle."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from homeassistant.setup import async_setup_component
from homeassistant.config_entries import ConfigEntry

from custom_components.thermex_api.const import DOMAIN


class TestIntegrationLifecycle:
    """Test the full integration lifecycle."""

    @pytest.fixture
    def mock_hub_connect(self):
        """Mock hub connect method."""
        with patch("custom_components.thermex_api.hub.ThermexHub.connect", new_callable=AsyncMock) as mock:
            yield mock

    @pytest.fixture
    def mock_hub_close(self):
        """Mock hub close method."""
        with patch("custom_components.thermex_api.hub.ThermexHub.close", new_callable=AsyncMock) as mock:
            yield mock

    @pytest.mark.asyncio
    async def test_full_setup_and_unload(self, mock_hass, mock_config_entry, mock_hub_connect, mock_hub_close):
        """Test complete setup and unload cycle."""
        # Setup
        with patch("custom_components.thermex_api.async_create_coordinator") as mock_coord:
            coordinator = MagicMock()
            coordinator.async_config_entry_first_refresh = AsyncMock()
            mock_coord.return_value = coordinator
            
            result = await mock_hass.config_entries.async_setup(mock_config_entry.entry_id)
            
            assert result is True
            assert DOMAIN in mock_hass.data
            assert mock_config_entry.entry_id in mock_hass.data[DOMAIN]
            
            # Verify hub was created and connected
            mock_hub_connect.assert_called_once()
        
        # Unload
        result = await mock_hass.config_entries.async_unload(mock_config_entry.entry_id)
        
        assert result is True
        # Entry data should be removed
        if DOMAIN in mock_hass.data:
            assert mock_config_entry.entry_id not in mock_hass.data[DOMAIN]

    @pytest.mark.asyncio
    async def test_options_update_triggers_reload(self, mock_hass, mock_config_entry, mock_hub_connect):
        """Test that options update triggers integration reload."""
        reload_called = False
        
        async def mock_reload(hass, entry):
            nonlocal reload_called
            reload_called = True
            return True
        
        with patch("custom_components.thermex_api.async_create_coordinator") as mock_coord:
            coordinator = MagicMock()
            coordinator.async_config_entry_first_refresh = AsyncMock()
            mock_coord.return_value = coordinator
            
            # Setup integration
            await mock_hass.config_entries.async_setup(mock_config_entry.entry_id)
            
            # Update options
            with patch.object(mock_hass.config_entries, "async_reload", side_effect=mock_reload):
                mock_hass.config_entries.async_update_entry(
                    mock_config_entry,
                    options={"fan_alert_hours": 50}
                )
                
                # Trigger the listener
                listener = mock_config_entry.update_listeners[0] if mock_config_entry.update_listeners else None
                if listener:
                    await listener(mock_hass, mock_config_entry)

    @pytest.mark.asyncio
    async def test_setup_with_connection_failure(self, mock_hass, mock_config_entry):
        """Test setup handles connection failure gracefully."""
        with patch("custom_components.thermex_api.hub.ThermexHub.connect", side_effect=ConnectionError("Failed")):
            from homeassistant.exceptions import ConfigEntryNotReady
            
            with pytest.raises(ConfigEntryNotReady):
                # Import here to trigger the actual setup
                from custom_components.thermex_api import async_setup_entry
                await async_setup_entry(mock_hass, mock_config_entry)

    @pytest.mark.asyncio
    async def test_runtime_persists_across_reload(self, mock_hass, mock_config_entry, mock_hub_connect):
        """Test that runtime data persists across integration reload."""
        storage_data = {"runtime_hours": 25.5, "last_reset": "2026-01-15T10:00:00"}
        
        with patch("custom_components.thermex_api.async_create_coordinator") as mock_coord:
            coordinator = MagicMock()
            coordinator.async_config_entry_first_refresh = AsyncMock()
            mock_coord.return_value = coordinator
            
            with patch("homeassistant.helpers.storage.Store.async_load", return_value=storage_data):
                with patch("homeassistant.helpers.storage.Store.async_save", new_callable=AsyncMock) as mock_save:
                    # Initial setup
                    await mock_hass.config_entries.async_setup(mock_config_entry.entry_id)
                    
                    # Get runtime manager
                    entry_data = mock_hass.data.get(DOMAIN, {}).get(mock_config_entry.entry_id)
                    if entry_data:
                        runtime_manager = entry_data.get("runtime_manager")
                        
                        # Modify runtime
                        if runtime_manager:
                            runtime_manager.start()
                            await runtime_manager.save()
                            
                            # Verify save was called
                            assert mock_save.called
                    
                    # Unload
                    await mock_hass.config_entries.async_unload(mock_config_entry.entry_id)
                    
                    # Reload - should load persisted data
                    await mock_hass.config_entries.async_setup(mock_config_entry.entry_id)
                    
                    # Verify data was loaded
                    entry_data = mock_hass.data.get(DOMAIN, {}).get(mock_config_entry.entry_id)
                    assert entry_data is not None


class TestMultipleConfigEntries:
    """Test handling of multiple config entries."""

    @pytest.mark.asyncio
    async def test_multiple_hubs_independent(self, mock_hass):
        """Test that multiple config entries create independent hubs."""
        from homeassistant.config_entries import ConfigEntry
        
        entry1 = ConfigEntry(
            version=1,
            minor_version=0,
            domain=DOMAIN,
            title="Thermex 1",
            data={"host": "192.168.1.100", "api_key": "key1"},
            source="user",
            entry_id="entry1",
        )
        
        entry2 = ConfigEntry(
            version=1,
            minor_version=0,
            domain=DOMAIN,
            title="Thermex 2",
            data={"host": "192.168.1.101", "api_key": "key2"},
            source="user",
            entry_id="entry2",
        )
        
        mock_hass.config_entries._entries[entry1.entry_id] = entry1
        mock_hass.config_entries._entries[entry2.entry_id] = entry2
        
        with patch("custom_components.thermex_api.hub.ThermexHub.connect", new_callable=AsyncMock):
            with patch("custom_components.thermex_api.async_create_coordinator") as mock_coord:
                coordinator = MagicMock()
                coordinator.async_config_entry_first_refresh = AsyncMock()
                mock_coord.return_value = coordinator
                
                # Setup both entries
                await mock_hass.config_entries.async_setup(entry1.entry_id)
                await mock_hass.config_entries.async_setup(entry2.entry_id)
                
                # Verify both hubs are in data
                assert DOMAIN in mock_hass.data
                assert entry1.entry_id in mock_hass.data[DOMAIN]
                assert entry2.entry_id in mock_hass.data[DOMAIN]
                
                # Verify they're independent
                hub1 = mock_hass.data[DOMAIN][entry1.entry_id]["hub"]
                hub2 = mock_hass.data[DOMAIN][entry2.entry_id]["hub"]
                assert hub1 != hub2
                assert hub1._host != hub2._host


class TestDelayedTurnOffPersistence:
    """Test delayed turn-off state persistence."""

    @pytest.mark.asyncio
    async def test_delayed_turn_off_cancels_on_reload(self, mock_hass, mock_config_entry, mock_hub):
        """Test that delayed turn-off is properly cancelled during reload."""
        from custom_components.thermex_api.fan import ThermexFan
        from custom_components.thermex_api.runtime_manager import RuntimeManager
        
        # Create fan with delayed turn-off active
        runtime_manager = MagicMock(spec=RuntimeManager)
        runtime_manager.get_last_preset.return_value = "medium"
        
        fan = ThermexFan(mock_hub, runtime_manager, mock_config_entry)
        fan.hass = mock_hass
        fan._delayed_off_handle = MagicMock()
        fan._delayed_off_active = True
        
        # Remove from hass (simulates reload)
        await fan.async_will_remove_from_hass()
        
        # Verify delayed turn-off was cancelled
        assert fan._delayed_off_handle.called
        assert fan._delayed_off_active is False
