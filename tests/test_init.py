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
        """Unloading closes the open runtime session, saves it and closes the hub."""
        runtime_manager = MagicMock()
        runtime_manager.save = AsyncMock()
        mock_config_entry.runtime_data = MagicMock(hub=mock_hub, runtime_manager=runtime_manager)

        with patch.object(mock_hass.config_entries, 'async_unload_platforms', new_callable=AsyncMock, return_value=True):
            result = await async_unload_entry(mock_hass, mock_config_entry)

        assert result is True
        runtime_manager.stop.assert_called_once()
        runtime_manager.save.assert_awaited_once()
        mock_hub.close.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_async_unload_entry_failure_keeps_hub(self, mock_hass, mock_config_entry, mock_hub):
        """A failed platform unload must not close the hub."""
        mock_config_entry.runtime_data = MagicMock(hub=mock_hub)

        with patch.object(mock_hass.config_entries, 'async_unload_platforms', new_callable=AsyncMock, return_value=False):
            result = await async_unload_entry(mock_hass, mock_config_entry)

        assert result is False
        mock_hub.close.assert_not_called()


class TestSetupErrorMessages:
    @pytest.mark.asyncio
    async def test_connect_failure_has_translated_message(self, mock_hass, mock_config_entry):
        from unittest.mock import AsyncMock, patch

        hub = MagicMock()
        hub.connect = AsyncMock(side_effect=OSError("down"))
        integration = MagicMock(version="1")
        with patch('custom_components.thermex_api.async_get_integration', return_value=integration), \
             patch('custom_components.thermex_api.ThermexHub', return_value=hub):
            with pytest.raises(ConfigEntryNotReady) as exc:
                await async_setup_entry(mock_hass, mock_config_entry)

        assert exc.value.translation_key == "cannot_connect"
        assert exc.value.translation_domain == "thermex_api"
        assert exc.value.translation_placeholders == {"host": "192.168.1.100"}


class TestMigration:
    @pytest.mark.asyncio
    async def test_v1_entry_keeps_existing_ids(self, mock_hass, mock_config_entry):
        """The id derived from the IP is frozen into the entry; registries stay valid."""
        from custom_components.thermex_api import async_migrate_entry

        mock_config_entry.version = 1
        mock_config_entry.data = {"host": "192.168.1.100", "api_key": "k"}

        assert await async_migrate_entry(mock_hass, mock_config_entry) is True

        kwargs = mock_hass.config_entries.async_update_entry.call_args.kwargs
        assert kwargs["data"]["device_id"] == "thermex_192_168_1_100"
        assert kwargs["unique_id"] == "thermex_192_168_1_100"
        assert kwargs["version"] == 2
        assert kwargs["data"]["host"] == "192.168.1.100"

    @pytest.mark.asyncio
    async def test_v2_entry_is_left_alone(self, mock_hass, mock_config_entry):
        from custom_components.thermex_api import async_migrate_entry

        mock_config_entry.version = 2

        assert await async_migrate_entry(mock_hass, mock_config_entry) is True
        mock_hass.config_entries.async_update_entry.assert_not_called()

    @pytest.mark.asyncio
    async def test_setup_passes_stored_device_id_to_hub(self, mock_hass, mock_config_entry):
        hub = MagicMock()
        hub.connect = AsyncMock()
        hub.close = AsyncMock()
        rm = MagicMock()
        rm.load = AsyncMock()
        mock_config_entry.data = {"host": "10.0.0.5", "api_key": "k", "device_id": "thermex_abc"}
        mock_hass.config_entries.async_forward_entry_setups = AsyncMock()

        with patch('custom_components.thermex_api.async_get_integration', return_value=MagicMock(version="1")), \
             patch('custom_components.thermex_api.ThermexHub', return_value=hub) as hub_cls, \
             patch('custom_components.thermex_api.RuntimeManager', return_value=rm), \
             patch('custom_components.thermex_api.Store'):
            await async_setup_entry(mock_hass, mock_config_entry)

        assert hub_cls.call_args.args[4] == "thermex_abc"


class TestRuntimeCheckpoint:
    """While the fan runs, the open session is saved regularly."""

    @pytest.fixture
    def mock_integration(self):
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

    @pytest.mark.asyncio
    async def test_setup_registers_the_checkpoint_timer(
        self, mock_hass, mock_config_entry, mock_hub, mock_runtime_manager, mock_integration
    ):
        from datetime import timedelta

        mock_hass.config_entries.async_forward_entry_setups = AsyncMock()
        mock_runtime_manager.save = AsyncMock()
        mock_runtime_manager.is_running = MagicMock(return_value=True)

        with patch('custom_components.thermex_api.async_get_integration', return_value=mock_integration), \
             patch('custom_components.thermex_api.ThermexHub', return_value=mock_hub), \
             patch('custom_components.thermex_api.RuntimeManager', return_value=mock_runtime_manager), \
             patch('custom_components.thermex_api.Store'), \
             patch('custom_components.thermex_api.async_track_time_interval') as track:
            await async_setup_entry(mock_hass, mock_config_entry)

        track.assert_called_once()
        assert track.call_args.args[2] == timedelta(seconds=600)
        mock_config_entry.async_on_unload.assert_called_once_with(track.return_value)

        callback = track.call_args.args[1]
        await callback(None)
        mock_runtime_manager.checkpoint.assert_called_once()
        mock_runtime_manager.save.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_checkpoint_is_skipped_while_the_fan_is_off(
        self, mock_hass, mock_config_entry, mock_hub, mock_runtime_manager, mock_integration
    ):
        mock_hass.config_entries.async_forward_entry_setups = AsyncMock()
        mock_runtime_manager.save = AsyncMock()
        mock_runtime_manager.is_running = MagicMock(return_value=False)

        with patch('custom_components.thermex_api.async_get_integration', return_value=mock_integration), \
             patch('custom_components.thermex_api.ThermexHub', return_value=mock_hub), \
             patch('custom_components.thermex_api.RuntimeManager', return_value=mock_runtime_manager), \
             patch('custom_components.thermex_api.Store'), \
             patch('custom_components.thermex_api.async_track_time_interval') as track:
            await async_setup_entry(mock_hass, mock_config_entry)

        await track.call_args.args[1](None)
        mock_runtime_manager.checkpoint.assert_not_called()
        mock_runtime_manager.save.assert_not_awaited()
