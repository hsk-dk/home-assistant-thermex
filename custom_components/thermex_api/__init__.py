# File: __init__.py
"""Thermex API integration."""
import logging

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers.storage import Store
from homeassistant.loader import async_get_integration

from .const import DOMAIN, RUNTIME_STORAGE_FILE, STARTUP, STORAGE_VERSION
from .data import ThermexConfigEntry, ThermexData
from .hub import ThermexAuthError, ThermexHub
from .runtime_manager import RuntimeManager

_LOGGER = logging.getLogger(__name__)

PLATFORMS = ["light", "fan", "sensor", "binary_sensor", "button"]


async def async_setup_entry(hass: HomeAssistant, entry: ThermexConfigEntry) -> bool:
    """Set up Thermex API from a config entry."""
    integration = await async_get_integration(hass, DOMAIN)
    _LOGGER.info(STARTUP, integration.version)

    host = entry.data["host"]
    api_key = entry.data["api_key"]

    # 1) Create and connect the Hub
    hub = ThermexHub(hass, host, api_key, entry.entry_id)
    try:
        await hub.connect()
    except ThermexAuthError as err:
        raise ConfigEntryAuthFailed(f"Thermex at {host} rejected the API password") from err
    except Exception as err:
        _LOGGER.error("Failed to connect to Thermex at %s: %s", host, err)
        raise ConfigEntryNotReady from err

    # If the hood later rejects the password (e.g. it was changed), start reauth
    hub.on_auth_failure = lambda: entry.async_start_reauth(hass)

    # Anything below can fail; never leave the websocket open if setup aborts
    try:
        # 2) Initialize & load the shared RuntimeManager
        store: Store = Store(
            hass,
            STORAGE_VERSION,
            RUNTIME_STORAGE_FILE.format(entry_id=entry.entry_id),
        )
        runtime_manager = RuntimeManager(store)
        await runtime_manager.load()
        hub.runtime_manager = runtime_manager

        # 3) Share hub + runtime manager with the platforms
        entry.runtime_data = ThermexData(hub=hub, runtime_manager=runtime_manager)

        # 4) Watch for options changes
        entry.async_on_unload(entry.add_update_listener(_async_update_listener))

        # 5) Forward setup to all platforms
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    except BaseException:
        await hub.close()
        raise
    return True


async def _async_update_listener(hass: HomeAssistant, entry: ThermexConfigEntry) -> None:
    """Reload the entry when options change."""
    _LOGGER.debug("Options updated, reloading Thermex entry %s", entry.entry_id)
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ThermexConfigEntry) -> bool:
    """Unload a config entry and clean up the hub."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        await entry.runtime_data.hub.close()
    return unload_ok
