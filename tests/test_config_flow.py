"""Tests for config flow."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.const import CONF_HOST

from custom_components.thermex_api.config_flow import ConfigFlow, OptionsFlowHandler
from custom_components.thermex_api.const import DOMAIN


class TestConfigFlow:
    """Test the config flow."""

    @pytest.fixture
    def mock_setup_entry(self):
        """Mock setting up an entry."""
        with patch(
            "custom_components.thermex_api.async_setup_entry",
            return_value=True,
        ) as mock_setup:
            yield mock_setup

    @pytest.mark.asyncio
    async def test_form_user(self, mock_hass):
        """Test we get the user form."""
        flow = ConfigFlow()
        flow.hass = mock_hass
        
        result = await flow.async_step_user()
        
        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == "user"

    @pytest.mark.asyncio
    async def test_form_user_with_valid_input(self, mock_hass, mock_setup_entry):
        """Test successful configuration with valid input."""
        flow = ConfigFlow()
        flow.hass = mock_hass
        mock_hass.data = {DOMAIN: {}}
        
        # Mock successful connection
        with patch(
            "custom_components.thermex_api.hub.ThermexHub.connect",
            return_value=None,
        ):
            result = await flow.async_step_user(
                user_input={
                    CONF_HOST: "192.168.1.100",
                    "api_key": "test_api_key",
                }
            )
        
        assert result["type"] == FlowResultType.CREATE_ENTRY
        assert result["data"][CONF_HOST] == "192.168.1.100"
        assert result["data"]["api_key"] == "test_api_key"

    @pytest.mark.asyncio
    async def test_form_user_connection_error(self, mock_hass):
        """Test connection error handling."""
        flow = ConfigFlow()
        flow.hass = mock_hass
        mock_hass.data = {DOMAIN: {}}
        
        # Mock failed connection
        with patch(
            "custom_components.thermex_api.hub.ThermexHub.connect",
            side_effect=Exception("Connection failed"),
        ):
            result = await flow.async_step_user(
                user_input={
                    CONF_HOST: "192.168.1.100",
                    "api_key": "test_api_key",
                }
            )
        
        assert result["type"] == FlowResultType.FORM
        assert result["errors"] == {"base": "cannot_connect"}

    @pytest.mark.asyncio
    async def test_hub_cleanup_on_connection_failure(self, mock_hass):
        """Test that hub is properly closed even when connection fails."""
        flow = ConfigFlow()
        flow.hass = mock_hass
        mock_hass.data = {DOMAIN: {}}
        
        # Create mock for hub.close() to verify it's called
        mock_close = AsyncMock()
        
        # Mock failed connection
        with patch(
            "custom_components.thermex_api.hub.ThermexHub.connect",
            side_effect=Exception("Connection failed"),
        ) as mock_connect, patch(
            "custom_components.thermex_api.hub.ThermexHub.close",
            new=mock_close,
        ):
            result = await flow.async_step_user(
                user_input={
                    CONF_HOST: "192.168.1.100",
                    "api_key": "test_api_key",
                }
            )
        
        # Verify hub.close() was called to prevent resource leak
        assert mock_close.called, "Hub close() should be called even on connection failure"
        assert result["type"] == FlowResultType.FORM
        assert result["errors"] == {"base": "cannot_connect"}

    @pytest.mark.asyncio
    async def test_hub_cleanup_on_success(self, mock_hass, mock_setup_entry):
        """Test that hub is properly closed even when connection succeeds."""
        flow = ConfigFlow()
        flow.hass = mock_hass
        mock_hass.data = {DOMAIN: {}}
        
        # Create mock for hub.close() to verify it's called
        mock_close = AsyncMock()
        
        # Mock successful connection
        with patch(
            "custom_components.thermex_api.hub.ThermexHub.connect",
            return_value=None,
        ) as mock_connect, patch(
            "custom_components.thermex_api.hub.ThermexHub.close",
            new=mock_close,
        ):
            result = await flow.async_step_user(
                user_input={
                    CONF_HOST: "192.168.1.100",
                    "api_key": "test_api_key",
                }
            )
        
        # Verify hub.close() was called to clean up temporary hub
        assert mock_close.called, "Hub close() should be called after successful validation"
        assert result["type"] == FlowResultType.CREATE_ENTRY

    @pytest.mark.asyncio
    async def test_options_flow(self, mock_config_entry):
        """Test options flow."""
        flow = OptionsFlowHandler(mock_config_entry)
        
        result = await flow.async_step_init(user_input=None)
        
        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == "init"

    @pytest.mark.asyncio
    async def test_options_flow_with_input(self, mock_config_entry):
        """Test options flow with valid input."""
        flow = OptionsFlowHandler(mock_config_entry)
        
        result = await flow.async_step_init(
            user_input={
                "fan_alert_hours": 120,
                "fan_alert_days": 100,
                "fan_auto_off_delay": 30,
                "enable_decolight": True,
            }
        )
        
        assert result["type"] == FlowResultType.CREATE_ENTRY
        assert result["data"]["fan_alert_hours"] == 120
        assert result["data"]["enable_decolight"] is True
