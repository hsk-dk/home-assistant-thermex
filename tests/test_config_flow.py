"""Tests for config flow."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.const import CONF_HOST, CONF_PORT

from custom_components.thermex_api.config_flow import ThermexApiConfigFlow
from custom_components.thermex_api.const import DOMAIN


class TestConfigFlow:
    """Test the config flow."""

    @pytest.fixture
    def mock_setup_entry(self):
        """Mock setup entry."""
        with patch("custom_components.thermex_api.async_setup_entry", return_value=True):
            yield

    @pytest.mark.asyncio
    async def test_form_user(self, mock_hass):
        """Test user form showing."""
        flow = ThermexApiConfigFlow()
        flow.hass = mock_hass
        
        result = await flow.async_step_user()
        
        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == "user"

    @pytest.mark.asyncio
    async def test_form_user_with_valid_input(self, mock_hass):
        """Test user form with valid input."""
        flow = ThermexApiConfigFlow()
        flow.hass = mock_hass
        
        with patch("custom_components.thermex_api.hub.ThermexHub.connect", return_value=True):
            with patch("custom_components.thermex_api.hub.ThermexHub.close"):
                result = await flow.async_step_user({
                    CONF_HOST: "192.168.1.100",
                    CONF_PORT: 4899,
                })
        
        assert result["type"] == FlowResultType.CREATE_ENTRY
        assert result["title"] == "Thermex API"
        assert result["data"][CONF_HOST] == "192.168.1.100"
        assert result["data"][CONF_PORT] == 4899

    @pytest.mark.asyncio
    async def test_form_user_with_connection_error(self, mock_hass):
        """Test user form with connection error."""
        flow = ThermexApiConfigFlow()
        flow.hass = mock_hass
        
        with patch("custom_components.thermex_api.hub.ThermexHub.connect", return_value=False):
            with patch("custom_components.thermex_api.hub.ThermexHub.close"):
                result = await flow.async_step_user({
                    CONF_HOST: "192.168.1.100",
                    CONF_PORT: 4899,
                })
        
        assert result["type"] == FlowResultType.CREATE_ENTRY
        assert result["errors"]["base"] == "cannot_connect"

    @pytest.mark.asyncio
    async def test_options_flow(self, mock_hass, mock_config_entry):
        """Test options flow."""
        flow = ThermexApiConfigFlow()
        flow.hass = mock_hass
        
        result = await flow.async_step_init(user_input=None)
        
        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == "init"

    @pytest.mark.asyncio
    async def test_options_flow_save(self, mock_hass, mock_config_entry):
        """Test options flow saves values."""
        flow = ThermexApiConfigFlow()
        flow.hass = mock_hass
        
        result = await flow.async_step_init(user_input={
            "enable_decolight": True,
            "delayed_off_timeout": 15,
        })
        
        assert result["type"] == FlowResultType.CREATE_ENTRY
