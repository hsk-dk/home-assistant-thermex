from __future__ import annotations

import asyncio
from typing import Any, Dict
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .thermex_api import ThermexApi

_LOGGER = logging.getLogger(__name__)
PLATFORMS: list[Platform] = [Platform.FAN]

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Thermex from a config entry."""
    hass.data.setdefault(DOMAIN, {})
    
    # Create and authenticate API instance
    _LOGGER.info("Creating API instance")
    api = ThermexApi(entry.data['host'], entry.data['code'])
    try:
        await api.connect()
        await api.authenticate()
    except Exception as e:
        # Handle connection/authentication errors
        # For example:
        _LOGGER.error(f"Failed to connect or authenticate: {e}")
        return False

    # Store API object for platforms to access
    hass.data[DOMAIN][entry.entry_id] = api

    # Forward entry setup to platforms
    await asyncio.gather(
        *[hass.config_entries.async_forward_entry_setup(entry, platform) for platform in PLATFORMS],
    )
    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    # Unload platforms
    unload_ok = await asyncio.gather(
        *[hass.config_entries.async_forward_entry_unload(entry, platform) for platform in PLATFORMS],
    )
    if unload_ok:
        # Remove API object
        api = hass.data[DOMAIN].pop(entry.entry_id)
        await api.close()
    return all(unload_ok)
