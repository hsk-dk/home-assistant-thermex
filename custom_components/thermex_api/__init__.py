# File: __init__.py
"""Thermex API integration."""
import logging

from homeassistant.components.fan import DOMAIN as FAN_DOMAIN
from homeassistant.const import CONF_DEVICE_ID
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import service
from homeassistant.helpers.storage import Store
from homeassistant.helpers.typing import ConfigType
from homeassistant.loader import async_get_integration

from .const import DOMAIN, RUNTIME_STORAGE_FILE, STARTUP, STORAGE_VERSION
from .data import ThermexConfigEntry, ThermexData
from .hub import ThermexAuthError, ThermexHub
from .runtime_manager import RuntimeManager

_LOGGER = logging.getLogger(__name__)

PLATFORMS = ["light", "fan", "sensor", "binary_sensor", "button"]

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

# action name -> method on the fan entity
FAN_ACTIONS = {
    "reset_runtime": "async_reset",
    "start_delayed_off": "start_delayed_off",
    "cancel_delayed_off": "cancel_delayed_off",
}


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Register the actions once, so they exist even before an entry is loaded."""
    for name, method in FAN_ACTIONS.items():
        service.async_register_platform_entity_service(
            hass,
            DOMAIN,
            name,
            entity_domain=FAN_DOMAIN,
            schema=None,
            func=method,
        )
    return True


async def async_migrate_entry(hass: HomeAssistant, entry: ThermexConfigEntry) -> bool:
    """Migrate old config entries.

    v1 -> v2: the ids of the device and all entities were derived from the host.
    Freeze that id into the entry so a later IP change no longer creates a new
    device and entities (nothing in the registries has to change), and stop using
    the IP address as the config entry's unique id.
    """
    if entry.version == 1:
        device_id = f"thermex_{entry.data['host'].replace('.', '_')}"
        hass.config_entries.async_update_entry(
            entry,
            data={**entry.data, CONF_DEVICE_ID: device_id},
            unique_id=device_id,
            version=2,
        )
        _LOGGER.debug("Migrated Thermex entry %s to version 2", entry.entry_id)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ThermexConfigEntry) -> bool:
    """Set up Thermex API from a config entry."""
    integration = await async_get_integration(hass, DOMAIN)
    _LOGGER.info(STARTUP, integration.version)

    host = entry.data["host"]
    api_key = entry.data["api_key"]

    # 1) Create and connect the Hub
    hub = ThermexHub(hass, host, api_key, entry.entry_id, entry.data.get(CONF_DEVICE_ID))
    try:
        await hub.connect()
    except ThermexAuthError as err:
        raise ConfigEntryAuthFailed(
            translation_domain=DOMAIN,
            translation_key="invalid_auth",
            translation_placeholders={"host": host},
        ) from err
    except Exception as err:
        raise ConfigEntryNotReady(
            translation_domain=DOMAIN,
            translation_key="cannot_connect",
            translation_placeholders={"host": host},
        ) from err

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

        # 4) Forward setup to all platforms (the options flow reloads the entry itself)
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    except BaseException:
        await hub.close()
        raise
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ThermexConfigEntry) -> bool:
    """Unload a config entry and clean up the hub."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        await entry.runtime_data.hub.close()
    return unload_ok
