"""Config and options flow for Thermex API."""
import logging
import uuid
from collections.abc import Mapping
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntry, ConfigFlowResult
from homeassistant.const import CONF_DEVICE_ID, CONF_HOST, CONF_MAC
from homeassistant.core import callback
from homeassistant.helpers.device_registry import format_mac
from homeassistant.helpers.service_info.dhcp import DhcpServiceInfo
from homeassistant.helpers.typing import UNDEFINED

from .const import DOMAIN
from .hub import ThermexAuthError, ThermexHub

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema({
    vol.Required("host"): str,
    vol.Required("api_key"): str,
})
STEP_DISCOVERY_DATA_SCHEMA = vol.Schema({vol.Required("api_key"): str})

async def _async_validate_connection(hass, host: str, api_key: str) -> str | None:
    """Try to connect; return an error key (or None on success)."""
    hub = ThermexHub(hass, host, api_key, "config_flow")
    try:
        await hub.connect()
    except ThermexAuthError:
        return "invalid_auth"
    except Exception as err:
        _LOGGER.debug("Unable to connect to Thermex: %s", err)
        return "cannot_connect"
    finally:
        # Always close the temporary hub to prevent resource leaks
        try:
            await hub.close()
        except Exception as err:
            _LOGGER.debug("Error closing temporary hub: %s", err)
    return None


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):  # type: ignore[call-arg]
    """Handle a config flow for Thermex API."""
    VERSION = 2

    def __init__(self) -> None:
        self._discovered_host: str | None = None
        self._discovered_mac: str | None = None

    async def async_step_user(self, user_input=None):
        if user_input is None:
            return self.async_show_form(
                step_id="user", data_schema=STEP_USER_DATA_SCHEMA
            )

        # One config entry per hood. The hood has no serial/MAC we can read, so
        # duplicates are detected by address, and a generated id (not the IP)
        # identifies the device and its entities from now on.
        self._async_abort_entries_match({CONF_HOST: user_input["host"]})
        device_id = f"thermex_{uuid.uuid4().hex[:12]}"
        await self.async_set_unique_id(device_id)

        error = await _async_validate_connection(
            self.hass, user_input["host"], user_input["api_key"]
        )
        if error:
            return self.async_show_form(
                step_id="user",
                data_schema=STEP_USER_DATA_SCHEMA,
                errors={"base": error},
            )

        return self.async_create_entry(
            title=user_input["host"],
            data={**user_input, CONF_DEVICE_ID: device_id},
        )

    async def async_step_dhcp(self, discovery_info: DhcpServiceInfo) -> ConfigFlowResult:
        """A device named Thermex-ESP showed up on the network.

        The hood has no serial number, but its MAC address identifies it. An existing
        hood is recognised by the MAC (and learns it the first time it is seen at its
        known address), so a new IP address from the router is followed automatically.
        """
        host = discovery_info.ip
        mac = format_mac(discovery_info.macaddress)

        for entry in self._async_current_entries(include_ignore=False):
            known_mac = entry.data.get(CONF_MAC)
            if known_mac == mac or (known_mac is None and entry.data.get(CONF_HOST) == host):
                return self.async_update_reload_and_abort(
                    entry,
                    data_updates={CONF_HOST: host, CONF_MAC: mac},
                    reason="already_configured",
                    reload_even_if_entry_is_unchanged=False,
                )

        # Also stops a second flow for the same hood, and a hood the user has ignored.
        await self.async_set_unique_id(mac)
        self._abort_if_unique_id_configured()

        self._discovered_host = host
        self._discovered_mac = mac
        self.context["title_placeholders"] = {"host": host}
        return await self.async_step_discovery_confirm()

    async def async_step_discovery_confirm(self, user_input=None) -> ConfigFlowResult:
        """Ask for the API password of a discovered hood."""
        assert self._discovered_host is not None
        errors: dict[str, str] = {}

        if user_input is not None:
            error = await _async_validate_connection(
                self.hass, self._discovered_host, user_input["api_key"]
            )
            if not error:
                device_id = f"thermex_{uuid.uuid4().hex[:12]}"
                await self.async_set_unique_id(device_id)
                return self.async_create_entry(
                    title=self._discovered_host,
                    data={
                        CONF_HOST: self._discovered_host,
                        "api_key": user_input["api_key"],
                        CONF_DEVICE_ID: device_id,
                        CONF_MAC: self._discovered_mac,
                    },
                )
            errors["base"] = error

        return self.async_show_form(
            step_id="discovery_confirm",
            data_schema=STEP_DISCOVERY_DATA_SCHEMA,
            description_placeholders={"host": self._discovered_host},
            errors=errors,
        )

    async def async_step_reconfigure(self, user_input=None):
        """Change the host and/or API password of an existing hood."""
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}

        if user_input is not None:
            host = user_input["host"]
            if any(
                other.entry_id != entry.entry_id and other.data.get("host") == host
                for other in self._async_current_entries()
            ):
                errors["base"] = "host_in_use"
            else:
                error = await _async_validate_connection(
                    self.hass, host, user_input["api_key"]
                )
                if error:
                    errors["base"] = error
                else:
                    return self.async_update_reload_and_abort(
                        entry,
                        title=host if entry.title == entry.data["host"] else UNDEFINED,
                        data_updates={"host": host, "api_key": user_input["api_key"]},
                    )

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=self.add_suggested_values_to_schema(
                STEP_USER_DATA_SCHEMA, user_input or entry.data
            ),
            errors=errors,
        )

    async def async_step_reauth(self, entry_data: Mapping[str, Any]):
        """Start reauthentication when the hood rejects the API password."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input=None):
        """Ask for a new API password."""
        reauth_entry = self._get_reauth_entry()
        errors: dict[str, str] = {}

        if user_input is not None:
            error = await _async_validate_connection(
                self.hass, reauth_entry.data["host"], user_input["api_key"]
            )
            if error:
                errors["base"] = error
            else:
                return self.async_update_reload_and_abort(
                    reauth_entry, data_updates={"api_key": user_input["api_key"]}
                )

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({vol.Required("api_key"): str}),
            description_placeholders={"host": reauth_entry.data["host"]},
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> "OptionsFlowHandler":
        return OptionsFlowHandler()


OPTIONS_SCHEMA = vol.Schema({
    vol.Optional("enable_decolight", default=False): bool,
    vol.Optional("fan_alert_hours", default=30): vol.All(int, vol.Range(min=1, max=1000)),
    vol.Optional("fan_alert_days", default=90): vol.All(int, vol.Range(min=1, max=365)),
    vol.Optional("fan_auto_off_delay", default=10): vol.All(int, vol.Range(min=1, max=120)),
})


class OptionsFlowHandler(config_entries.OptionsFlowWithReload):
    """Options; Home Assistant reloads the entry when they change."""

    async def async_step_init(self, user_input=None):
        """Manage options for Thermex integration."""
        if user_input is not None:
            return self.async_create_entry(title="Options", data=user_input)

        return self.async_show_form(
            step_id="init",
            data_schema=self.add_suggested_values_to_schema(
                OPTIONS_SCHEMA, self.config_entry.options
            ),
        )
