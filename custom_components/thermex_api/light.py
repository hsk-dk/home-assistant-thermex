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
from .const import DOMAIN, THERMEX_NOTIFY

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass, entry, async_add_entities):
    """Setup Thermex main and deco lights."""
    entry_data = hass.data[DOMAIN][entry.entry_id]
    hub: ThermexHub = entry_data["hub"]
    enable_decolight = entry.options.get("enable_decolight", False)
    entities: list[LightEntity] = [ThermexLight(hub)]
    if enable_decolight:
        entities.append(ThermexDecoLight(hub))
    async_add_entities(entities, update_before_add=True)

class ThermexLight(LightEntity):
    """Main light entity for Thermex hood."""
    _attr_supported_color_modes = {ColorMode.BRIGHTNESS}
    _attr_color_mode = ColorMode.BRIGHTNESS

    def __init__(self, hub: ThermexHub):
        self._hub = hub
        self._attr_unique_id = f"{hub.unique_id}_light"
        self._attr_translation_key = "thermex_light"
        self._is_on: bool = False
        self._brightness: int = 25
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
        self._got_initial_state = False
        self._unsub = async_dispatcher_connect(self.hass, THERMEX_NOTIFY, self._handle_notify)
        _LOGGER.debug("ThermexLight: awaiting initial notify for state")
        async_call_later(self.hass, 10, self._fallback_status)

    async def async_will_remove_from_hass(self):
        if self._unsub:
            self._unsub()

    def _handle_notify(self, ntf_type: str, data: dict) -> None:
        if ntf_type.lower() != "light":
            _LOGGER.debug("ThermexLight received non-light notify: %s", data)
            return
        light = data.get("Light")
        if light is None:
            _LOGGER.warning("ThermexLight notify missing 'Light' key: %s", data)
            return
        self._is_on = bool(light.get("lightonoff", 0))
        self._brightness = max(0, min(255, light.get("lightbrightness", 0)))
        self._got_initial_state = True
        self.schedule_update_ha_state()

    async def async_turn_on(self, **kwargs):
        brightness = kwargs.get(ATTR_BRIGHTNESS, self._brightness)
        brightness = max(0, min(255, brightness))  # Clamp to valid range
        _LOGGER.debug("ThermexLight: Turn on - Brightness: %s", brightness)
        await self._hub.send_request("Update", {"Light": {"lightonoff": 1, "lightbrightness": brightness}})
        self._is_on = True
        self._brightness = brightness
        self.schedule_update_ha_state()

    async def async_turn_off(self, **kwargs):
        await self._hub.send_request("Update", {"Light": {"lightonoff": 0, "lightbrightness": 0}})
        self._is_on = False
        self._brightness = 0
        self.schedule_update_ha_state()

    async def _fallback_status(self, _now):
        if self._got_initial_state:
            return
        _LOGGER.warning("ThermexLight: no notify in 10s, fetching fallback status")
        try:
            resp = await self._hub.send_request("status", {})
            light = resp.get("Data", {}).get("Light", {})
            self._is_on = bool(light.get("lightonoff", 0))
            self._brightness = max(0, min(255, light.get("lightbrightness", 0)))
            self._got_initial_state = True
            self.schedule_update_ha_state()
        except Exception as err:
            _LOGGER.error("ThermexLight: fallback status failed: %s", err)

class ThermexDecoLight(LightEntity):
    """Deco light entity for Thermex hood."""
    _attr_supported_color_modes = {ColorMode.HS, ColorMode.BRIGHTNESS}
    _attr_color_mode = ColorMode.HS

    def __init__(self, hub: ThermexHub):
        self._hub = hub
        self._attr_unique_id = f"{hub.unique_id}_decolight"
        self._attr_translation_key = "thermex_decolight"
        self._is_on: bool = False
        self._brightness: int = 0
        self._hs_color: tuple[float, float] = (0.0, 0.0)
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

    @property
    def hs_color(self) -> tuple[float, float]:
        return self._hs_color

    async def async_added_to_hass(self):
        self._got_initial_state = False
        self._unsub = async_dispatcher_connect(self.hass, THERMEX_NOTIFY, self._handle_notify)
        _LOGGER.debug("ThermexDecoLight: awaiting initial notify for state")
        async_call_later(self.hass, 10, self._fallback_status)

    async def async_will_remove_from_hass(self):
        if self._unsub:
            self._unsub()

    def _handle_notify(self, ntf_type: str, data: dict) -> None:
        if ntf_type.lower() != "decolight":
            _LOGGER.debug("ThermexDecoLight received non-decolight notify: %s", data)
            return
        deco = data.get("Decolight")
        if deco is None:
            _LOGGER.warning("ThermexDecoLight notify missing 'Decolight' key: %s", data)
            return
        self._is_on = bool(deco.get("decolightonoff", 0))
        self._brightness = max(0, min(255, deco.get("decolightbrightness", 0)))
        r = deco.get("decolightr", 0)
        g = deco.get("decolightg", 0)
        b = deco.get("decolightb", 0)
        self._hs_color = color_RGB_to_hs(r, g, b)
        self._got_initial_state = True
        self.schedule_update_ha_state()

    async def async_turn_on(self, **kwargs):
        brightness = kwargs.get(ATTR_BRIGHTNESS, self._brightness)
        brightness = max(0, min(255, brightness))  # Clamp to valid range
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
        self._hs_color = color_RGB_to_hs(r, g, b)
        self.schedule_update_ha_state()

    async def async_turn_off(self, **kwargs):
        await self._hub.send_request("Update", {"Decolight": {"decolightonoff": 0, "decolightbrightness": 0}})
        self._is_on = False
        self._brightness = 0
        self.schedule_update_ha_state()

    async def _fallback_status(self, _now):
        if self._got_initial_state:
            return
        _LOGGER.warning("ThermexDecoLight: no notify in 10s, fetching fallback status")
        try:
            resp = await self._hub.send_request("status", {})
            deco = resp.get("Data", {}).get("Decolight", {})
            self._is_on = bool(deco.get("decolightonoff", 0))
            self._brightness = max(0, min(255, deco.get("decolightbrightness", 0)))
            r = deco.get("decolightr", 0)
            g = deco.get("decolightg", 0)
            b = deco.get("decolightb", 0)
            self._hs_color = color_RGB_to_hs(r, g, b)
            self._got_initial_state = True
            self.schedule_update_ha_state()
        except Exception as err:
            _LOGGER.error("ThermexDecoLight: fallback status failed: %s", err)
