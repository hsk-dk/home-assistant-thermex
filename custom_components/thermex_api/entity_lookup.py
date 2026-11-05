"""Helpers for finding this integration's entities."""
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from .const import DOMAIN


def find_fan_entity_id(hass: HomeAssistant, hub_unique_id: str) -> str | None:
    """Return the fan's entity_id via the entity registry (survives user renames)."""
    return er.async_get(hass).async_get_entity_id("fan", DOMAIN, f"{hub_unique_id}_fan")
