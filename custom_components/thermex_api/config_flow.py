"""Config and options flow for Thermex API."""
import logging

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntry

from .const import DOMAIN
from .hub import ThermexHub

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema({
    vol.Required("host"): str,
    vol.Required("api_key"): str,
})

class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Thermex API."""
    VERSION = 1

    async def async_step_user(self, user_input=None):
        if user_input is None:
            return self.async_show_form(
                step_id="user", data_schema=STEP_USER_DATA_SCHEMA
            )

        # Create a temporary ID for setup verification
        temp_entry_id = self.hass.data.get(DOMAIN, {}).get("tmp_id", 0) + 1
        self.hass.data.setdefault(DOMAIN, {})["tmp_id"] = temp_entry_id
        
        hub = ThermexHub(self.hass, user_input["host"], user_input["api_key"], f"tmp_{temp_entry_id}")
        try:
            await hub.connect()
        except Exception as err:
            _LOGGER.error("Unable to connect to Thermex: %s", err)
            return self.async_show_form(
                step_id="user",
                data_schema=STEP_USER_DATA_SCHEMA,
                errors={"base": "cannot_connect"},
            )
        finally:
            # Always close the temporary hub to prevent resource leaks
            try:
                await hub.close()
            except Exception as err:
                _LOGGER.debug("Error closing temporary hub: %s", err)

        return self.async_create_entry(
            title=user_input["host"], data=user_input
        )

    @staticmethod
    def async_get_options_flow(entry: ConfigEntry):
        return OptionsFlowHandler(entry)


class OptionsFlowHandler(config_entries.OptionsFlow):
    def __init__(self, entry: ConfigEntry):
        self.entry = entry

    async def async_step_init(self, user_input=None):
        """Manage options for Thermex integration."""
        if user_input is None:
            data_schema = vol.Schema({
                vol.Optional(
                    "enable_decolight",
                    default=self.entry.options.get("enable_decolight", False)
                ): bool,
                vol.Optional(
                    "fan_alert_hours",
                    default=self.entry.options.get("fan_alert_hours", 30)
                ): vol.All(int, vol.Range(min=1, max=1000)),
                vol.Optional(
                    "fan_alert_days",
                    default=self.entry.options.get("fan_alert_days", 90)
                ): vol.All(int, vol.Range(min=1, max=365)),
                vol.Optional(
                    "fan_auto_off_delay",
                    default=self.entry.options.get("fan_auto_off_delay", 10)
                ): vol.All(int, vol.Range(min=1, max=120)),
            })
            return self.async_show_form(
                step_id="init", data_schema=data_schema
            )

        return self.async_create_entry(title="Options", data=user_input)
