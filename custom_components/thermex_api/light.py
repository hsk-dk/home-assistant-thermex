# File: custom_components/thermex_api/light.py

import logging
from homeassistant.components.light import (
    LightEntity,
    ATTR_BRIGHTNESS,
    ATTR_RGB_COLOR,
    ColorMode,
)
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.util.color import color_RGB_to_hs, color_hs_to_RGB
from homeassistant.helpers.event import async_call_later

from .hub import ThermexHub
from .const import (
    DOMAIN,
    THERMEX_NOTIFY,
    DEFAULT_BRIGHTNESS,
    MIN_BRIGHTNESS,
    MAX_BRIGHTNESS,
    FALLBACK_STATUS_TIMEOUT,
)

_LOGGER = logging.getLogger(__name__)

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

async def async_setup_entry(hass, entry, async_add_entities):
    """Setup Thermex main and deco lights."""
    entry_data = hass.data[DOMAIN][entry.entry_id]
    hub: ThermexHub = entry_data["hub"]
    enable_decolight = entry.options.get("enable_decolight", False)
    entities: list[LightEntity] = [ThermexLight(hub)]
    if enable_decolight:
        entities.append(ThermexDecoLight(hub))
    async_add_entities(entities, update_before_add=True)

class ThermexLightBase(LightEntity):
    """Base class for Thermex light entities with common functionality."""

    def __init__(self, hub: ThermexHub, unique_id_suffix: str, translation_key: str):
        """Initialize the base light entity."""
        self._hub = hub
        self._attr_unique_id = f"{hub.unique_id}_{unique_id_suffix}"
        self._attr_translation_key = translation_key
        self._attr_has_entity_name = True
        self._is_on: bool = False
        self._brightness: int = DEFAULT_BRIGHTNESS
        self._last_brightness: int = DEFAULT_BRIGHTNESS
        self._unsub = None
        self._got_initial_state: bool = False

    @property
    def device_info(self) -> DeviceInfo:
        return self._hub.device_info

    @property
    def is_on(self) -> bool:
        return self._is_on

    @property
    def brightness(self) -> int:
        return self._brightness

    async def async_added_to_hass(self):
        """Called when entity is added to hass."""
        self._got_initial_state = False
        self._unsub = async_dispatcher_connect(self.hass, THERMEX_NOTIFY, self._handle_notify)
        _LOGGER.debug("%s: awaiting initial notify for state", self.__class__.__name__)
        async_call_later(self.hass, FALLBACK_STATUS_TIMEOUT, self._fallback_status)

    async def async_will_remove_from_hass(self):
        """Called when entity is being removed from hass."""
        if self._unsub:
            self._unsub()

    def _clamp_brightness(self, brightness: int) -> int:
        """Clamp brightness to valid range."""
        return max(MIN_BRIGHTNESS, min(MAX_BRIGHTNESS, brightness))

    async def _fallback_status(self, _now):
        """Request fallback status if no initial notify received."""
        if self._got_initial_state:
            return
        
        if self._hub.startup_complete:
            _LOGGER.debug("%s: Hub startup complete but no notify received, using default state", 
                         self.__class__.__name__)
            self._got_initial_state = True
            return
            
        _LOGGER.warning("%s: no notify in %ss, fetching fallback status", 
                       self.__class__.__name__, FALLBACK_STATUS_TIMEOUT)
        try:
            data = await self._hub.request_fallback_status(self.__class__.__name__)
            self._process_fallback_data(data)
            self._got_initial_state = True
            self.schedule_update_ha_state()
        except Exception as err:
            _LOGGER.error("%s: fallback status failed: %s", self.__class__.__name__, err)
            self._got_initial_state = True

    def _process_fallback_data(self, data: dict):
        """Process fallback status data. Override in subclasses."""
        raise NotImplementedError

    def _handle_notify(self, ntf_type: str, data: dict) -> None:
        """Handle notifications from the hub. Override in subclasses."""
        raise NotImplementedError


class ThermexLight(ThermexLightBase):
    """Main light entity for Thermex hood."""
    _attr_supported_color_modes = {ColorMode.BRIGHTNESS}
    _attr_color_mode = ColorMode.BRIGHTNESS

    def __init__(self, hub: ThermexHub):
        super().__init__(hub, "light", "thermex_light")

    def _handle_notify(self, ntf_type: str, data: dict) -> None:
        """Handle light notifications from the hub."""
        if ntf_type.lower() != "light":
            _LOGGER.debug("ThermexLight received non-light notify: %s", data)
            return
        
        light = data.get("Light")
        if light is None:
            _LOGGER.warning("ThermexLight notify missing 'Light' key: %s", data)
            return
        
        if not self._got_initial_state:
            _LOGGER.debug("ThermexLight: Received initial state via notify")
            self._got_initial_state = True
            
        self._is_on = bool(light.get("lightonoff", 0))
        brightness = self._clamp_brightness(light.get("lightbrightness", 0))
        self._brightness = brightness
        if self._is_on and brightness > 0:
            self._last_brightness = brightness
        self.schedule_update_ha_state()

    async def async_turn_on(self, **kwargs):
        """Turn on the light."""
        brightness = kwargs.get(ATTR_BRIGHTNESS, self._last_brightness)
        brightness = self._clamp_brightness(brightness)
        api_brightness = _to_api_brightness(brightness)
        
        _LOGGER.debug("ThermexLight: Turn on - HA Brightness: %s, API Brightness: %s", brightness, api_brightness)
        await self._hub.send_request("Update", {
            "Light": {"lightonoff": 1, "lightbrightness": api_brightness}
        })
        
        self._is_on = True
        self._brightness = brightness
        if brightness > 0:
            self._last_brightness = brightness
        self.schedule_update_ha_state()

    async def async_turn_off(self, **kwargs):
        """Turn off the light."""
        await self._hub.send_request("Update", {
            "Light": {"lightonoff": 0, "lightbrightness": 1}
        })
        self._is_on = False
        self._brightness = MIN_BRIGHTNESS
        self.schedule_update_ha_state()

    def _process_fallback_data(self, data: dict):
        """Process fallback status data for main light."""
        light = data.get("Light", {})
        if not light:
            _LOGGER.debug("ThermexLight: No light data in fallback response, using defaults")
            return
            
        self._is_on = bool(light.get("lightonoff", 0))
        brightness = self._clamp_brightness(light.get("lightbrightness", 0))
        self._brightness = brightness
        if self._is_on and brightness > 0:
            self._last_brightness = brightness


class ThermexDecoLight(ThermexLightBase):
    """Deco light entity for Thermex hood."""
    _attr_supported_color_modes = {ColorMode.HS, ColorMode.BRIGHTNESS}
    _attr_color_mode = ColorMode.HS

    def __init__(self, hub: ThermexHub):
        super().__init__(hub, "decolight", "thermex_decolight")
        self._hs_color: tuple[float, float] = (0.0, 0.0)

    @property
    def hs_color(self) -> tuple[float, float]:
        return self._hs_color

    def _handle_notify(self, ntf_type: str, data: dict) -> None:
        """Handle decolight notifications from the hub."""
        if ntf_type.lower() != "decolight":
            _LOGGER.debug("ThermexDecoLight received non-decolight notify: %s", data)
            return
        
        deco = data.get("Decolight")
        if deco is None:
            _LOGGER.warning("ThermexDecoLight notify missing 'Decolight' key: %s", data)
            return
        
        self._is_on = bool(deco.get("decolightonoff", 0))
        api_brightness = deco.get("decolightbrightness", 1)
        brightness = self._clamp_brightness(_to_ha_brightness(api_brightness))
        self._brightness = brightness
        if self._is_on and brightness > 0:
            self._last_brightness = brightness
        
        r = deco.get("decolightr", 0)
        g = deco.get("decolightg", 0)
        b = deco.get("decolightb", 0)
        self._hs_color = color_RGB_to_hs(r, g, b)
        self._got_initial_state = True
        self.schedule_update_ha_state()

    async def async_turn_on(self, **kwargs):
        """Turn on the deco light."""
        brightness = kwargs.get(ATTR_BRIGHTNESS, self._last_brightness)
        brightness = self._clamp_brightness(brightness)
        
        rgb = kwargs.get(ATTR_RGB_COLOR)
        if rgb:
            r, g, b = rgb
        else:
            r, g, b = color_hs_to_RGB(*self._hs_color)
        
        payload = {
            "decolightonoff": 1,
            "decolightbrightness": brightness,
            "decolightr": r,
            "decolightg": g,
            "decolightb": b,
        }
        await self._hub.send_request("Update", {"Decolight": payload})
        
        self._is_on = True
        self._brightness = brightness
        if brightness > 0:
            self._last_brightness = brightness
        self._hs_color = color_RGB_to_hs(r, g, b)
        self.schedule_update_ha_state()

    async def async_turn_off(self, **kwargs):
        """Turn off the deco light."""
        await self._hub.send_request("Update", {
            "Decolight": {"decolightonoff": 0, "decolightbrightness": 1}
        })
        self._is_on = False
        self._brightness = MIN_BRIGHTNESS
        self.schedule_update_ha_state()

    def _process_fallback_data(self, data: dict):
        """Process fallback status data for deco light."""
        deco = data.get("Decolight", {})
        if not deco:
            _LOGGER.debug("ThermexDecoLight: No decolight data in fallback response, using defaults")
            return
            
        self._is_on = bool(deco.get("decolightonoff", 0))
        api_brightness = deco.get("decolightbrightness", 1)
        brightness = self._clamp_brightness(_to_ha_brightness(api_brightness))
        self._brightness = brightness
        if self._is_on and brightness > 0:
            self._last_brightness = brightness
        
        r = deco.get("decolightr", 0)
        g = deco.get("decolightg", 0)
        b = deco.get("decolightb", 0)
        self._hs_color = color_RGB_to_hs(r, g, b)
