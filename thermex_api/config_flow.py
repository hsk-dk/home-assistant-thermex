"""Config flow for Thermex integration."""
import logging
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from .const import DOMAIN

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

            if await self._authenticate(self.host, self.password):
                await self.async_set_unique_id(f"thermex_{self.host}")
                self._abort_if_unique_id_configured()

                return self.async_create_entry(title=f"Thermex {self.host}", data=user_input)
            else:
                errors["base"] = "auth_failed"

        return self.async_show_form(step_id="user", data_schema=DATA_SCHEMA, errors=errors)

    async def async_step_reauth(self, entry_data):
        self.host = entry_data["host"]
        self.context["title_placeholders"] = {"host": self.host}
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input=None):
        errors = {}

        if user_input is not None:
            self.password = user_input["password"]

            if await self._authenticate(self.host, self.password):
                existing_entry = await self.async_set_unique_id(f"thermex_{self.host}")
                if existing_entry:
                    self.hass.config_entries.async_update_entry(
                        existing_entry, data={"host": self.host, "password": self.password}
                    )
                    await self.hass.config_entries.async_reload(existing_entry.entry_id)
                return self.async_abort(reason="reauth_successful")
            else:
                errors["base"] = "auth_failed"

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({vol.Required("password"): str}),
            errors=errors,
        )

    async def _authenticate(self, host, password):
        # Simulate API authentication
        _LOGGER.debug("Attempting authentication with host: %s", host)
        try:
            return True if password else False  # Replace with real API call
        except Exception as e:
            _LOGGER.error("Authentication error: %s", str(e))
            return False