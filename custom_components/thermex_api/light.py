# File: custom_components/thermex_api/light.py

import logging
from typing import ClassVar

from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_HS_COLOR,
    ATTR_RGB_COLOR,
    ColorMode,
    LightEntity,
)
from homeassistant.core import callback
from homeassistant.util.color import color_hs_to_RGB, color_RGB_to_hs

from .const import (
    DEFAULT_BRIGHTNESS,
    MAX_BRIGHTNESS,
    MIN_BRIGHTNESS,
)
from .coordinator import ThermexCoordinator
from .data import ThermexConfigEntry
from .entity import ThermexEntity
from .state import DecolightState, LightState

_LOGGER = logging.getLogger(__name__)

PARALLEL_UPDATES = 1

def _to_api_brightness(ha_brightness: int) -> int:
    """Convert Home Assistant brightness (0-255) to API brightness (1-100).
    
    Note: Home Assistant brightness of 0 is mapped to API brightness of 1 (minimum).
    This is intentional because the API doesn't accept 0 as a valid brightness value.
    To turn off the light, use the turn_off() method which sets lightonoff=0.
    
    Args:
        ha_brightness: Home Assistant brightness value (0-255)
        
    Returns:
        API brightness value (1-100)
    """
    if ha_brightness == 0:
        return 1  # API minimum - API doesn't accept 0
    return max(1, min(100, round(ha_brightness / 255 * 100)))

def _to_ha_brightness(api_brightness: int) -> int:
    """Convert API brightness (1-100) to Home Assistant brightness (0-255).
    
    Args:
        api_brightness: API brightness value (1-100)
        
    Returns:
        Home Assistant brightness value (0-255)
    """
    return round(api_brightness / 100 * 255)

async def async_setup_entry(hass, entry: ThermexConfigEntry, async_add_entities):
    """Setup Thermex main and deco lights."""
    coordinator = entry.runtime_data.coordinator

    entities: list[LightEntity] = [ThermexLight(coordinator)]
    if entry.options.get("enable_decolight", False):
        entities.append(ThermexDecoLight(coordinator))
    async_add_entities(entities)


def _clamp_brightness(brightness: int) -> int:
    """Clamp brightness to the Home Assistant range."""
    return max(MIN_BRIGHTNESS, min(MAX_BRIGHTNESS, brightness))


class ThermexLightBase(ThermexEntity, LightEntity):
    """Base class for Thermex light entities with common functionality."""

    def __init__(self, coordinator: ThermexCoordinator, unique_id_suffix: str, translation_key: str):
        """Initialize the base light entity."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{self._hub.unique_id}_{unique_id_suffix}"
        self._attr_translation_key = translation_key
        # The hood reports brightness 0 while off; remember the last real one
        self._last_brightness: int = DEFAULT_BRIGHTNESS
        self._remember()

    @property
    def _section(self) -> LightState | DecolightState | None:
        """The hood's reported state of this light."""
        raise NotImplementedError

    @property
    def is_on(self) -> bool:
        return bool(self._section and self._section.on)

    @property
    def brightness(self) -> int:
        section = self._section
        if section and section.on and section.brightness > 0:
            return _clamp_brightness(_to_ha_brightness(section.brightness))
        return self._last_brightness

    def _remember(self) -> None:
        """Keep what the hood forgets while the light is off."""
        section = self._section
        if section and section.on and section.brightness > 0:
            self._last_brightness = self.brightness

    @callback
    def _handle_coordinator_update(self) -> None:
        self._remember()
        super()._handle_coordinator_update()


class ThermexLight(ThermexLightBase):
    """Main light entity for Thermex hood."""
    _attr_supported_color_modes: ClassVar[set[ColorMode]] = {ColorMode.BRIGHTNESS}
    _attr_color_mode = ColorMode.BRIGHTNESS

    def __init__(self, coordinator: ThermexCoordinator):
        super().__init__(coordinator, "light", "thermex_light")

    @property
    def _section(self) -> LightState | None:
        return self.coordinator.data.light if self.coordinator.data else None

    async def async_turn_on(self, **kwargs):
        """Turn on the light."""
        brightness = _clamp_brightness(kwargs.get(ATTR_BRIGHTNESS, self._last_brightness))
        api_brightness = _to_api_brightness(brightness)

        _LOGGER.debug("ThermexLight: Turn on - HA Brightness: %s, API Brightness: %s", brightness, api_brightness)
        # State is updated from the Status read-back the hub dispatches: the
        # hood may clamp or rewrite what we sent.
        await self._hub.send_update({
            "Light": {"lightonoff": 1, "lightbrightness": api_brightness}
        })

    async def async_turn_off(self, **kwargs):
        """Turn off the light."""
        await self._hub.send_update({
            "Light": {"lightonoff": 0, "lightbrightness": 1}
        })


class ThermexDecoLight(ThermexLightBase):
    """Deco light entity for Thermex hood."""
    # HS already implies brightness support; HA rejects HS combined with BRIGHTNESS
    _attr_supported_color_modes: ClassVar[set[ColorMode]] = {ColorMode.HS}
    _attr_color_mode = ColorMode.HS

    def __init__(self, coordinator: ThermexCoordinator):
        self._hs_color: tuple[float, float] = (0.0, 0.0)
        super().__init__(coordinator, "decolight", "thermex_decolight")

    @property
    def _section(self) -> DecolightState | None:
        return self.coordinator.data.decolight if self.coordinator.data else None

    @property
    def hs_color(self) -> tuple[float, float]:
        return self._hs_color

    def _remember(self) -> None:
        """Keep the last real colour: the hood reports 0,0,0 while it is off."""
        super()._remember()
        section = self._section
        if section and section.on and any(section.rgb):
            self._hs_color = color_RGB_to_hs(*section.rgb)

    async def async_turn_on(self, **kwargs):
        """Turn on the deco light."""
        brightness = _clamp_brightness(kwargs.get(ATTR_BRIGHTNESS, self._last_brightness))

        rgb = kwargs.get(ATTR_RGB_COLOR)
        hs = kwargs.get(ATTR_HS_COLOR)
        if rgb:
            r, g, b = rgb
        elif hs:
            r, g, b = color_hs_to_RGB(*hs)
        else:
            r, g, b = color_hs_to_RGB(*self._hs_color)

        payload = {
            "decolightonoff": 1,
            "decolightbrightness": _to_api_brightness(brightness),
            "decolightr": r,
            "decolightg": g,
            "decolightb": b,
        }
        await self._hub.send_update({"Decolight": payload})

    async def async_turn_off(self, **kwargs):
        """Turn off the deco light."""
        await self._hub.send_update({
            "Decolight": {"decolightonoff": 0, "decolightbrightness": 1}
        })
