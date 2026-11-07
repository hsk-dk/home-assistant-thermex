"""Tests for config flow."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.const import CONF_HOST

from custom_components.thermex_api.config_flow import ConfigFlow, OptionsFlowHandler
from custom_components.thermex_api.const import DOMAIN


class TestConfigFlow:
    """Test the config flow."""

    @pytest.mark.asyncio
    async def test_duplicate_host_aborts(self, mock_hass):
        """The same hood (address) cannot be added twice."""
        from homeassistant.data_entry_flow import AbortFlow

        flow = ConfigFlow()
        flow.hass = mock_hass
        flow.async_set_unique_id = AsyncMock()
        flow._async_abort_entries_match = MagicMock(side_effect=AbortFlow("already_configured"))

        with patch("custom_components.thermex_api.hub.ThermexHub.connect") as connect:
            with pytest.raises(AbortFlow):
                await flow.async_step_user(
                    user_input={CONF_HOST: "192.168.1.100", "api_key": "k", "enable_decolight": False}
                )

        flow._async_abort_entries_match.assert_called_once_with({CONF_HOST: "192.168.1.100"})
        connect.assert_not_called()

    @pytest.mark.asyncio
    async def test_new_entry_gets_generated_id_not_the_ip(self, mock_hass):
        import re

        flow = ConfigFlow()
        flow.hass = mock_hass
        flow.async_set_unique_id = AsyncMock()
        flow._async_abort_entries_match = MagicMock()

        with patch("custom_components.thermex_api.hub.ThermexHub.connect", return_value=None):
            result = await flow.async_step_user(
                user_input={CONF_HOST: "192.168.1.100", "api_key": "k", "enable_decolight": False}
            )

        device_id = result["data"]["device_id"]
        assert re.fullmatch(r"thermex_[0-9a-f]{12}", device_id)
        assert "192" not in device_id
        flow.async_set_unique_id.assert_awaited_once_with(device_id)
        assert result["data"]["host"] == "192.168.1.100"

    @pytest.mark.asyncio
    @pytest.mark.parametrize("decolight", [True, False])
    async def test_the_decolight_is_chosen_when_the_hood_is_added(self, mock_hass, decolight):
        flow = ConfigFlow()
        flow.hass = mock_hass
        flow.async_set_unique_id = AsyncMock()
        flow._async_abort_entries_match = MagicMock()

        with patch("custom_components.thermex_api.hub.ThermexHub.connect", return_value=None):
            result = await flow.async_step_user(
                user_input={CONF_HOST: "192.168.1.100", "api_key": "k", "enable_decolight": decolight}
            )

        assert result["options"] == {"enable_decolight": decolight}
        assert "enable_decolight" not in result["data"]

    def test_the_decolight_is_off_unless_asked_for(self):
        from custom_components.thermex_api.config_flow import STEP_USER_DATA_SCHEMA

        assert STEP_USER_DATA_SCHEMA({CONF_HOST: "h", "api_key": "k"})["enable_decolight"] is False

    def test_reconfigure_does_not_ask_for_the_decolight(self):
        from custom_components.thermex_api.config_flow import STEP_RECONFIGURE_DATA_SCHEMA

        assert "enable_decolight" not in {str(k) for k in STEP_RECONFIGURE_DATA_SCHEMA.schema}

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
        flow.async_set_unique_id = AsyncMock()
        flow._abort_if_unique_id_configured = MagicMock()
        
        result = await flow.async_step_user()
        
        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == "user"

    @pytest.mark.asyncio
    async def test_form_user_with_valid_input(self, mock_hass, mock_setup_entry):
        """Test successful configuration with valid input."""
        flow = ConfigFlow()
        flow.hass = mock_hass
        flow.async_set_unique_id = AsyncMock()
        flow._abort_if_unique_id_configured = MagicMock()
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
                    "enable_decolight": False,
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
        flow.async_set_unique_id = AsyncMock()
        flow._abort_if_unique_id_configured = MagicMock()
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
                    "enable_decolight": False,
                }
            )
        
        assert result["type"] == FlowResultType.FORM
        assert result["errors"] == {"base": "cannot_connect"}

    @pytest.mark.asyncio
    async def test_hub_cleanup_on_connection_failure(self, mock_hass):
        """Test that hub is properly closed even when connection fails."""
        flow = ConfigFlow()
        flow.hass = mock_hass
        flow.async_set_unique_id = AsyncMock()
        flow._abort_if_unique_id_configured = MagicMock()
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
                    "enable_decolight": False,
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
        flow.async_set_unique_id = AsyncMock()
        flow._abort_if_unique_id_configured = MagicMock()
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
                    "enable_decolight": False,
                }
            )
        
        # Verify hub.close() was called to clean up temporary hub
        assert mock_close.called, "Hub close() should be called after successful validation"
        assert result["type"] == FlowResultType.CREATE_ENTRY

    @pytest.mark.asyncio
    async def test_options_flow(self, mock_hass, mock_config_entry):
        """Test options flow."""
        flow = OptionsFlowHandler()
        flow.hass = mock_hass
        flow.handler = mock_config_entry.entry_id
        mock_hass.config_entries.async_get_known_entry = MagicMock(return_value=mock_config_entry)
        
        result = await flow.async_step_init(user_input=None)
        
        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == "init"

    @pytest.mark.asyncio
    async def test_options_flow_with_input(self, mock_hass, mock_config_entry):
        """Test options flow with valid input."""
        flow = OptionsFlowHandler()
        flow.hass = mock_hass
        flow.handler = mock_config_entry.entry_id
        mock_hass.config_entries.async_get_known_entry = MagicMock(return_value=mock_config_entry)
        
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


class TestReauthFlow:
    """Reauthentication and error mapping."""

    @pytest.mark.asyncio
    async def test_invalid_password_shows_invalid_auth(self, mock_hass):
        from custom_components.thermex_api.hub import ThermexAuthError

        flow = ConfigFlow()
        flow.hass = mock_hass
        flow.async_set_unique_id = AsyncMock()
        flow._abort_if_unique_id_configured = MagicMock()

        with patch("custom_components.thermex_api.hub.ThermexHub.connect", side_effect=ThermexAuthError("x")):
            result = await flow.async_step_user(
                user_input={CONF_HOST: "192.168.1.100", "api_key": "wrong"}
            )

        assert result["type"] == FlowResultType.FORM
        assert result["errors"] == {"base": "invalid_auth"}

    @pytest.mark.asyncio
    async def test_reauth_updates_password(self, mock_hass, mock_config_entry):
        flow = ConfigFlow()
        flow.hass = mock_hass
        flow._get_reauth_entry = MagicMock(return_value=mock_config_entry)
        flow.async_update_reload_and_abort = MagicMock(return_value={"type": "abort"})

        with patch("custom_components.thermex_api.hub.ThermexHub.connect", return_value=None):
            result = await flow.async_step_reauth_confirm(user_input={"api_key": "new_key"})

        assert result == {"type": "abort"}
        flow.async_update_reload_and_abort.assert_called_once_with(
            mock_config_entry, data_updates={"api_key": "new_key"}
        )

    @pytest.mark.asyncio
    async def test_reauth_wrong_password_shows_error(self, mock_hass, mock_config_entry):
        from custom_components.thermex_api.hub import ThermexAuthError

        flow = ConfigFlow()
        flow.hass = mock_hass
        flow._get_reauth_entry = MagicMock(return_value=mock_config_entry)

        with patch("custom_components.thermex_api.hub.ThermexHub.connect", side_effect=ThermexAuthError("x")):
            result = await flow.async_step_reauth_confirm(user_input={"api_key": "still_wrong"})

        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == "reauth_confirm"
        assert result["errors"] == {"base": "invalid_auth"}

    @pytest.mark.asyncio
    async def test_reauth_form_shown_first(self, mock_hass, mock_config_entry):
        flow = ConfigFlow()
        flow.hass = mock_hass
        flow._get_reauth_entry = MagicMock(return_value=mock_config_entry)

        result = await flow.async_step_reauth({"host": "x"})

        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == "reauth_confirm"


def test_options_flow_reloads_entry_automatically():
    from homeassistant.config_entries import OptionsFlowWithReload

    assert issubclass(OptionsFlowHandler, OptionsFlowWithReload)
    assert isinstance(ConfigFlow.async_get_options_flow(MagicMock()), OptionsFlowHandler)


class TestReconfigureFlow:
    @pytest.fixture
    def flow(self, mock_hass, mock_config_entry):
        mock_config_entry.title = "192.168.1.100"
        flow = ConfigFlow()
        flow.hass = mock_hass
        flow._get_reconfigure_entry = MagicMock(return_value=mock_config_entry)
        flow._async_current_entries = MagicMock(return_value=[mock_config_entry])
        flow.async_update_reload_and_abort = MagicMock(return_value={"type": "abort"})
        return flow

    @pytest.mark.asyncio
    async def test_form_is_prefilled(self, flow):
        result = await flow.async_step_reconfigure()

        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == "reconfigure"

    @pytest.mark.asyncio
    async def test_new_host_updates_entry_and_title(self, flow, mock_config_entry):
        with patch("custom_components.thermex_api.hub.ThermexHub.connect", return_value=None):
            result = await flow.async_step_reconfigure(
                user_input={"host": "192.168.1.200", "api_key": "new"}
            )

        assert result == {"type": "abort"}
        args, kwargs = flow.async_update_reload_and_abort.call_args
        assert args[0] is mock_config_entry
        assert kwargs["data_updates"] == {"host": "192.168.1.200", "api_key": "new"}
        assert kwargs["title"] == "192.168.1.200"  # title followed the old host

    @pytest.mark.asyncio
    async def test_custom_title_is_kept(self, flow, mock_config_entry):
        from homeassistant.helpers.typing import UNDEFINED

        mock_config_entry.title = "Kitchen hood"
        with patch("custom_components.thermex_api.hub.ThermexHub.connect", return_value=None):
            await flow.async_step_reconfigure(user_input={"host": "192.168.1.200", "api_key": "k"})

        assert flow.async_update_reload_and_abort.call_args.kwargs["title"] is UNDEFINED

    @pytest.mark.asyncio
    async def test_same_host_is_allowed_for_a_password_change(self, flow):
        with patch("custom_components.thermex_api.hub.ThermexHub.connect", return_value=None):
            await flow.async_step_reconfigure(user_input={"host": "192.168.1.100", "api_key": "new"})

        flow.async_update_reload_and_abort.assert_called_once()

    @pytest.mark.asyncio
    async def test_host_used_by_another_entry_is_rejected(self, flow, mock_config_entry):
        other = MagicMock(entry_id="other", data={"host": "192.168.1.201"})
        flow._async_current_entries = MagicMock(return_value=[mock_config_entry, other])

        result = await flow.async_step_reconfigure(
            user_input={"host": "192.168.1.201", "api_key": "k"}
        )

        assert result["errors"] == {"base": "host_in_use"}
        flow.async_update_reload_and_abort.assert_not_called()

    @pytest.mark.asyncio
    async def test_unreachable_host_shows_error(self, flow):
        with patch("custom_components.thermex_api.hub.ThermexHub.connect", side_effect=OSError("x")):
            result = await flow.async_step_reconfigure(
                user_input={"host": "192.168.1.250", "api_key": "k"}
            )

        assert result["errors"] == {"base": "cannot_connect"}
        flow.async_update_reload_and_abort.assert_not_called()
