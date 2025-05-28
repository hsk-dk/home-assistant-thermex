"""Config flow for Thermex integration."""
import logging
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from .const import DOMAIN
from .api import ThermexAPI, ThermexAuthError, ThermexConnectionError  # Make sure ThermexConnectionError is imported

_LOGGER = logging.getLogger(__name__)

DATA_SCHEMA = vol.Schema(
    {
        vol.Required("host"): str,
        vol.Required("password"): str,
    }
)

class ThermexConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Thermex."""

    VERSION = 1

    def __init__(self):
        self.host = None
        self.password = None
        self.entry = None

    async def async_step_user(self, user_input=None):
        errors = {}

        if user_input is not None:
            self.host = user_input["host"]
            self.password = user_input["password"]
            api = ThermexAPI(self.host, self.password)

            try:
                await api.connect(self.hass)  # Connect and authenticate
                await api.authenticate()
                await self.async_set_unique_id(f"thermex_{self.host}")
                # Fix: return after abort to avoid continuing the flow
                abort_result = self._abort_if_unique_id_configured()
                if abort_result is not None:
                    return abort_result
                return self.async_create_entry(title=f"Thermex {self.host}", data=user_input)
            except ThermexAuthError:
                _LOGGER.debug("Authentication failed for Thermex at %s", self.host)
                errors["base"] = "auth_failed"
            except ThermexConnectionError:
                _LOGGER.debug("Could not connect to Thermex at %s", self.host)
                errors["base"] = "cannot_connect"
            except Exception as ex:
                _LOGGER.exception("Unknown error in Thermex config flow: %s", ex)
                errors["base"] = "unknown"

        return self.async_show_form(step_id="user", data_schema=DATA_SCHEMA, errors=errors)

    async def async_step_reauth(self, entry_data):
        self.host = entry_data["host"]
        self.context["title_placeholders"] = {"host": self.host}
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input=None):
        errors = {}

        if user_input is not None:
            self.password = user_input["password"]

            api = ThermexAPI(self.host, self.password)
            try:
                await api.connect(self.hass)
                await api.authenticate()
                existing_entry = await self.async_set_unique_id(f"thermex_{self.host}")
                if existing_entry:
                    self.hass.config_entries.async_update_entry(
                        existing_entry, data={"host": self.host, "password": self.password}
                    )
                    return self.async_abort(reason="reauth_successful")
            except ThermexAuthError:
                _LOGGER.debug("Reauthentication failed for Thermex at %s", self.host)
                errors["base"] = "auth_failed"
            except ThermexConnectionError:
                _LOGGER.debug("Could not connect to Thermex at %s during reauth", self.host)
                errors["base"] = "cannot_connect"
            except Exception as ex:
                _LOGGER.exception("Unknown error in Thermex reauth flow: %s", ex)
                errors["base"] = "unknown"

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({vol.Required("password"): str}),
            errors=errors,
        )
