"""Tests for config flow."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from homeassistant import data_entry_flow
from homeassistant.const import CONF_HOST, CONF_PORT

from custom_components.thermex_api.config_flow import ThermexConfigFlow
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
        flow = ThermexConfigFlow()
        flow.hass = mock_hass
        
        result = await flow.async_step_user()
        
        assert result["type"] == data_entry_flow.RESULT_TYPE_FORM
        assert result["step_id"] == "user"

    @pytest.mark.asyncio
    async def test_form_user_with_valid_input(self, mock_hass, mock_setup_entry):
        """Test successful configuration with valid input."""
        flow = ThermexConfigFlow()
        flow.hass = mock_hass
        mock_hass.data = {DOMAIN: {}}
        
        # Mock successful connection
        with patch(
            "custom_components.thermex_api.hub.ThermexHub.test_connection",
            return_value=True,
        ):
            result = await flow.async_step_user(
                user_input={
                    CONF_HOST: "192.168.1.100",
                    CONF_PORT: 20000,
                }
            )
        
        assert result["type"] == data_entry_flow.RESULT_TYPE_CREATE_ENTRY
        assert result["title"] == "Thermex Hood"
        assert result["data"][CONF_HOST] == "192.168.1.100"
        assert result["data"][CONF_PORT] == 20000

    @pytest.mark.asyncio
    async def test_form_user_connection_error(self, mock_hass):
        """Test connection error handling."""
        flow = ThermexConfigFlow()
        flow.hass = mock_hass
        
        # Mock failed connection
        with patch(
            "custom_components.thermex_api.hub.ThermexHub.test_connection",
            side_effect=Exception("Connection failed"),
        ):
            result = await flow.async_step_user(
                user_input={
                    CONF_HOST: "192.168.1.100",
                    CONF_PORT: 20000,
                }
            )
        
        assert result["type"] == data_entry_flow.RESULT_TYPE_FORM
        assert result["errors"] == {"base": "cannot_connect"}

    @pytest.mark.asyncio
    async def test_options_flow(self, mock_config_entry):
        """Test options flow."""
        flow = ThermexConfigFlow()
        
        result = await flow.async_step_init(user_input=None)
        
        assert result["type"] == data_entry_flow.RESULT_TYPE_FORM
        assert result["step_id"] == "init"

    @pytest.mark.asyncio
    async def test_options_flow_with_input(self, mock_config_entry):
        """Test options flow with valid input."""
        flow = ThermexConfigFlow()
        
        result = await flow.async_step_init(
            user_input={
                "fan_alert_hours": 120,
                "fan_alert_days": 100,
                "fan_auto_off_delay": 30,
                "enable_decolight": True,
            }
        )
        
        assert result["type"] == data_entry_flow.RESULT_TYPE_CREATE_ENTRY
        assert result["data"]["fan_alert_hours"] == 120
        assert result["data"]["enable_decolight"] is True

    @pytest.mark.asyncio
    async def test_options_flow_validates_ranges(self, mock_config_entry):
        """Test options flow validates input ranges."""
        flow = ThermexConfigFlow()
        
        # Test with invalid hours (too high)
        result = await flow.async_step_init(
            user_input={
                "fan_alert_hours": 2000,  # Max is 1000
                "fan_alert_days": 100,
                "fan_auto_off_delay": 30,
            }
        )
        
        # Should show form again with validation error
        assert result["type"] == data_entry_flow.RESULT_TYPE_FORM
