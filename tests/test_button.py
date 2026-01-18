"""Tests for button entities."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from custom_components.thermex_api.button import (
    ResetRuntimeButton,
    DelayedTurnOffButton,
    async_setup_entry,
)


class TestButtonSetup:
    """Test button setup."""

    @pytest.mark.asyncio
    async def test_async_setup_entry(self, mock_hass, mock_hub, mock_config_entry):
        """Test button setup from config entry."""
        runtime_manager = MagicMock()
        mock_hass.data = {
            "thermex_api": {
                mock_config_entry.entry_id: {
                    "hub": mock_hub,
                    "runtime_manager": runtime_manager,
                }
            }
        }
        
        async_add_entities = AsyncMock()
        
        await async_setup_entry(mock_hass, mock_config_entry, async_add_entities)
        
        async_add_entities.assert_called_once()
        entities = async_add_entities.call_args[0][0]
        assert len(entities) == 2
        assert isinstance(entities[0], ResetRuntimeButton)
        assert isinstance(entities[1], DelayedTurnOffButton)


class TestResetRuntimeButton:
    """Test ResetRuntimeButton entity."""

    @pytest.fixture
    def button_entity(self, mock_hub, mock_hass):
        """Create a ResetRuntimeButton entity."""
        runtime_manager = MagicMock()
        runtime_manager.reset = MagicMock()
        runtime_manager.save = AsyncMock()
        
        button = ResetRuntimeButton(mock_hub, runtime_manager, "test_entry_id")
        button.hass = mock_hass
        return button

    def test_button_initialization(self, button_entity, mock_hub):
        """Test button entity initialization."""
        assert button_entity._hub == mock_hub
        assert button_entity._entry_id == "test_entry_id"
        assert button_entity.icon == "mdi:refresh"

    @pytest.mark.asyncio
    async def test_button_press_resets_runtime(self, button_entity, mock_hass):
        """Test pressing button resets runtime."""
        mock_hass.data = {
            "thermex_api": {
                "test_entry_id": MagicMock()
            }
        }
        
        await button_entity.async_press()
        
        button_entity._runtime_manager.reset.assert_called_once()
        button_entity._runtime_manager.save.assert_called_once()

    @pytest.mark.asyncio
    async def test_button_press_with_no_runtime_manager(self, mock_hub, mock_hass):
        """Test button press handles missing runtime manager gracefully."""
        button = ResetRuntimeButton(mock_hub, None, "test_entry_id")
        button.hass = mock_hass
        
        # Should not raise an error
        await button.async_press()


class TestDelayedTurnOffButton:
    """Test DelayedTurnOffButton entity."""

    @pytest.fixture
    def delayed_button(self, mock_hub, mock_hass):
        """Create a DelayedTurnOffButton entity."""
        button = DelayedTurnOffButton(mock_hub, "test_entry_id")
        button.hass = mock_hass
        button.hass.services = MagicMock()
        button.hass.services.async_call = AsyncMock()
        return button

    def test_delayed_button_initialization(self, delayed_button, mock_hub):
        """Test delayed button entity initialization."""
        assert delayed_button._hub == mock_hub
        assert delayed_button._entry_id == "test_entry_id"
        assert delayed_button.icon == "mdi:timer-off"

    @pytest.mark.asyncio
    async def test_delayed_button_press_domain_service(self, delayed_button):
        """Test pressing delayed turn off button calls domain service."""
        await delayed_button.async_press()
        
        delayed_button.hass.services.async_call.assert_called()
        call_args = delayed_button.hass.services.async_call.call_args[0]
        assert call_args[0] == "thermex_api"  # domain
        assert call_args[1] == "start_delayed_off_domain"  # service
