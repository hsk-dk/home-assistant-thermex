# File: __init__.py
"""Thermex API integration."""
import logging
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.loader import async_get_integration
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.helpers.storage import Store

from .const import DOMAIN, STARTUP, STORAGE_VERSION, RUNTIME_STORAGE_FILE
from .hub import ThermexHub
from .runtime_manager import RuntimeManager

_LOGGER = logging.getLogger(__name__)


async def async_create_coordinator(hass: HomeAssistant, hub: ThermexHub) -> DataUpdateCoordinator:
    async def async_update_data():
        try:
            return hub.get_coordinator_data()
        except Exception as err:
            raise UpdateFailed(f"Failed to fetch data: {err}") from err

    return DataUpdateCoordinator(
        hass,
        _LOGGER,
        name="thermex_coordinator",
        update_method=async_update_data,
        update_interval=timedelta(seconds=30),
    )


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Thermex API from a config entry."""
    integration = await async_get_integration(hass, DOMAIN)
    _LOGGER.info(STARTUP, integration.version)

    host = entry.data["host"]
    api_key = entry.data["api_key"]

    # 1) Create and connect the Hub
    hub = ThermexHub(hass, host, api_key, entry.entry_id)
    try:
        await hub.connect()
    except Exception as err:
        _LOGGER.error("Failed to connect to Thermex at %s: %s", host, err)
        raise ConfigEntryNotReady from err

    # 2) Prepare per-entry storage in hass.data
    hass.data.setdefault(DOMAIN, {})
    entry_data: dict = {}
    entry_data["hub"] = hub

    # 3) Initialize & load the shared RuntimeManager
    store: Store = Store(
        hass,
        STORAGE_VERSION,
        RUNTIME_STORAGE_FILE.format(entry_id=entry.entry_id),
    )
    runtime_manager = RuntimeManager(store, hub)
    await runtime_manager.load()
    hub.runtime_manager = runtime_manager
    entry_data["runtime_manager"] = runtime_manager

    # 4) Create & refresh the coordinator
    coordinator = await async_create_coordinator(hass, hub)
    await coordinator.async_config_entry_first_refresh()
    entry_data["coordinator"] = coordinator

    # 5) Save entry_data back into hass.data
    hass.data[DOMAIN][entry.entry_id] = entry_data

    # 6) Watch for options changes
    entry.async_on_unload(
        entry.add_update_listener(_async_update_listener)
    )

    # 7) Forward setup to all platforms
    await hass.config_entries.async_forward_entry_setups(
        entry,
        ["light", "fan", "sensor", "binary_sensor", "button"],
    )
    return True


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload the entry when options change."""
    _LOGGER.debug("Options updated, reloading Thermex entry %s", entry.entry_id)
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry and clean up the hub."""
    unload_ok = await hass.config_entries.async_unload_platforms(
        entry, ["light", "fan", "sensor", "binary_sensor", "button"]
    )
    # Drop our per-entry dict (hub, coordinator, runtime_manager)
    hass.data[DOMAIN].pop(entry.entry_id, None)
    # Also remove the global coordinator key - OBS must be remove at some point
    hass.data[DOMAIN].pop("coordinator", None)
    return unload_ok
