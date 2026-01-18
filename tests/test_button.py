"""Tests for button entities."""
import pytest
from unittest.mock import AsyncMock, patch

from custom_components.thermex_api.button import (
    ThermexResetRuntimeButton,
    ThermexDelayedOffButton,
    async_setup_entry,
)


class TestButtonSetup:
    """Test button setup."""

    @pytest.mark.asyncio
    async def test_async_setup_entry(self, mock_hass, mock_hub, mock_config_entry):
        """Test button setup."""
        mock_hass.data = {
            "thermex_api": {
                mock_config_entry.entry_id: {
                    "hub": mock_hub,
                }
            }
        }
        
        async_add_entities = AsyncMock()
        await async_setup_entry(mock_hass, mock_config_entry, async_add_entities)
        
        entities = async_add_entities.call_args[0][0]
        assert len(entities) == 2
        assert isinstance(entities[0], ThermexResetRuntimeButton)
        assert isinstance(entities[1], ThermexDelayedOffButton)


class TestResetRuntimeButton:
    """Test ThermexResetRuntimeButton entity."""

    @pytest.fixture
    def button_entity(self, mock_hub, mock_hass):
        """Create a ThermexResetRuntimeButton entity."""
        button = ThermexResetRuntimeButton(mock_hub)
        button.hass = mock_hass
        return button

    def test_button_initialization(self, button_entity, mock_hub):
        """Test button entity initialization."""
        assert button_entity._hub == mock_hub
        assert "Reset Runtime" in button_entity.name

    @pytest.mark.asyncio
    async def test_button_press_calls_service(self, button_entity, mock_hass):
        """Test button press calls reset service."""
        with patch.object(mock_hass.services, 'async_call', new_callable=AsyncMock) as mock_call:
            await button_entity.async_press()
            
            mock_call.assert_called_once()
            call_args = mock_call.call_args
            assert call_args[0][0] == "thermex_api"
            assert call_args[0][1] == "reset_runtime"


class TestDelayedOffButton:
    """Test ThermexDelayedOffButton entity."""

    @pytest.fixture
    def button_entity(self, mock_hub, mock_hass):
        """Create a ThermexDelayedOffButton entity."""
        button = ThermexDelayedOffButton(mock_hub)
        button.hass = mock_hass
        return button

    def test_button_initialization(self, button_entity, mock_hub):
        """Test button entity initialization."""
        assert button_entity._hub == mock_hub
        assert "Delayed Off" in button_entity.name

    @pytest.mark.asyncio
    async def test_button_press_calls_service(self, button_entity, mock_hass):
        """Test button press calls delayed off service."""
        with patch.object(mock_hass.services, 'async_call', new_callable=AsyncMock) as mock_call:
            await button_entity.async_press()
            
            mock_call.assert_called_once()
            call_args = mock_call.call_args
            assert call_args[0][0] == "thermex_api"
            assert call_args[0][1] == "delayed_off"
