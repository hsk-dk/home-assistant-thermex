import asyncio
import logging

from .const import DOMAIN
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.typing import ConfigType

from .api import ThermexAPI, ThermexConnectionError, ThermexAuthError
from .const import __version__
_LOGGER = logging.getLogger(__name__)
_LOGGER.info("Setting up Thermex integration v%s", __version__)
async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the Thermex integration."""
    hass.data.setdefault(DOMAIN, {})
    return True

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Set up Thermex integration from a config entry."""
    hass.data.setdefault(DOMAIN, {})
    host = entry.data.get("host")
    password = entry.data.get("password")

    api = ThermexAPI(host, password)

    try:
        await api.connect(hass)
        status = await api.get_status()
        _LOGGER.debug("Initial Thermex status: %s", status)

        # Store API and status data in hass.data
        hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
            "api": api,
            "status": status,
            "listeners": []
        }

        # Start background listener for Notify updates
        hass.loop.create_task(_thermex_notify_listener(hass, entry.entry_id, api))

        # Forward entry to platforms
        for platform in ("light", "sensor", "switch"):
            hass.async_create_task(
                hass.config_entries.async_forward_entry_setup(entry, platform)
            )

        return True

    except ThermexAuthError:
        _LOGGER.error("Authentication with Thermex failed.")
        return False
    except ThermexConnectionError:
        _LOGGER.error("Connection to Thermex WebSocket failed.")
        return False
    except Exception as e:
        _LOGGER.exception("Unexpected error during Thermex setup: %s", str(e))
        return False

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Unload a config entry."""
    data = hass.data.get(DOMAIN, {}).pop(entry.entry_id, {})
    api = data.get("api")
    if api:
        await api.close()

    unload_ok = all(
        await asyncio.gather(
            *[hass.config_entries.async_forward_entry_unload(entry, platform)
              for platform in ("light", "sensor", "switch")]
        )
    )
    return unload_ok

async def _thermex_notify_listener(hass: HomeAssistant, entry_id: str, api: ThermexAPI):
    """Background task that listens for Notify messages from the API."""
    try:
        async for notify in api.listen():
            _LOGGER.debug("Received Notify: %s", notify)
            data = notify.get("Data", {})

            # Update the latest cached status
            hass.data[DOMAIN][entry_id]["status"].update(data)

            # Notify registered listeners (entities)
            for update_callback in hass.data[DOMAIN][entry_id]["listeners"]:
                hass.async_create_task(update_callback())

    except Exception as e:
        _LOGGER.error("Notify listener stopped due to error: %s", e)
