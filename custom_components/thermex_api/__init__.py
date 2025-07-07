# File: __init__.py
"""Thermex API integration."""
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.loader import async_get_integration

from .const import DOMAIN, STARTUP
from .hub import ThermexHub

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Thermex API from a config entry."""
    integration = await async_get_integration(hass, DOMAIN)
    _LOGGER.info(STARTUP, integration.version)
    host = entry.data["host"]
    api_key = entry.data["api_key"]

    hub = ThermexHub(hass, host, api_key)
    try:
        await hub.connect()
    except Exception as err:
        _LOGGER.error("Failed to connect to Thermex at %s: %s", host, err)
        raise ConfigEntryNotReady from err

    # Store hub instance for this entry
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = hub

    # Reload integration when options change
    entry.async_on_unload(
        entry.add_update_listener(_async_update_listener)
    )
    # Forward setup to all platforms
    await hass.config_entries.async_forward_entry_setups(
        entry, ["light", "fan", "sensor", "binary_sensor","button"]
    )
    return True

async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle options update by reloading the entry."""
    _LOGGER.debug("Options updated, reloading Thermex entry %s", entry.entry_id)
    await hass.config_entries.async_reload(entry.entry_id)

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry and clean up the hub."""
    unload_ok = await hass.config_entries.async_unload_platforms(
        entry, ["light", "fan", "sensor", "binary_sensor"]
    )
    hub: ThermexHub = hass.data[DOMAIN].pop(entry.entry_id)
    await hub.close()
    return unload_ok
