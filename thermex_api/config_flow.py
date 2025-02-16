"""Config flow for Thermex_fan integration."""
import logging
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.loader import Integration
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

DATA_SCHEMA = vol.Schema(
    {
        vol.Required("host", description={"suggested_value": "example.com"}): str,
        vol.Required("password", description={"suggested_value": ""}): str,
    }
)

class ThermexConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    async def async_step_user(self, user_input=None):
        errors = {}

        if user_input is not None:
            host = user_input['host']
            password = user_input['password']

            # Your authentication logic goes here
            
            # If authentication is successful
            unique_id = f"thermex_{host}"
            name = "Thermex"

            await self.async_set_unique_id(unique_id)
            self._abort_if_unique_id_configured()

            self.context["title_placeholders"] = {"unique_id": unique_id}

            # Create entry with device name and data
            return self.async_create_entry(title=name, data=user_input)

        return self.async_show_form(
            step_id="user",
            data_schema=DATA_SCHEMA,
            errors=errors,
            description_placeholders={
                "title": await self.hass.components.frontend.async_get_translations(self.hass, "config_flow", "title"),
                "description": await self.hass.components.frontend.async_get_translations(self.hass, "config_flow", "description"),
                "host_label": await self.hass.components.frontend.async_get_translations(self.hass, "config_flow", "host_label"),
                "password_label": await self.hass.components.frontend.async_get_translations(self.hass, "config_flow", "password_label"),
            }
        )
