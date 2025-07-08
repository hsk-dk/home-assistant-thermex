# File: light.py
from homeassistant.components.light import (
    LightEntity,
    ATTR_BRIGHTNESS,
    ATTR_RGB_COLOR,
    ColorMode,
)
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.util.color import color_RGB_to_hs, color_hs_to_RGB

from .hub import ThermexHub
from .const import DOMAIN, THERMEX_NOTIFY
import asyncio
import logging

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass, entry, async_add_entities):
    """Set up light entities with optional deco-light support based on entry options."""
    hub: ThermexHub = hass.data[DOMAIN][entry.entry_id]
    enable_decolight = entry.options.get("enable_decolight", False)
    entities: list[LightEntity] = [ThermexLight(hub)]
    if enable_decolight:
        entities.append(ThermexDecoLight(hub))
    async_add_entities(entities, update_before_add=True)

class ThermexLight(LightEntity):
    """Main hood light actuator."""
    _attr_name = "Thermex Light"
    _attr_supported_color_modes = {ColorMode.BRIGHTNESS}
    _attr_color_mode = ColorMode.BRIGHTNESS
    def __init__(self, hub: ThermexHub):
        self._hub = hub
        self._attr_unique_id = f"{hub.unique_id}_light"
        self._is_on = False
        self._brightness = 0
        self._unsub = None

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self._hub.unique_id)},
            manufacturer="Thermex",
            name=f"Thermex Hood ({self._hub._host})",
            model="ESP-API",
        )

    @property
    def is_on(self) -> bool:
        return self._is_on

    @property
    def brightness(self) -> int:
        return self._brightness

    async def async_added_to_hass(self):
        """Subscribe first, then fetch initial state without blowing up on timeout."""
        # 1) Early subscribe to notifications
        self._unsub = async_dispatcher_connect(
            self.hass, THERMEX_NOTIFY, self._handle_notify
        )

        # 2) Fetch initial state
        try:
            resp = await self._hub.send_request("Status", {})
            _LOGGER.debug("ThermexLight: initial STATUS response: %s", resp)
            light = resp.get("Data", {}).get("Light", {})
            self._is_on = bool(light.get("lightonoff", 0))
            self._brightness = light.get("lightbrightness", 0)
        except asyncio.TimeoutError:
            _LOGGER.warning(
                "ThermexLight: initial STATUS timed out, deferring state until notify"
            )
        except Exception as err:
            _LOGGER.error("ThermexLight: error fetching initial STATUS: %s", err)

    async def async_will_remove_from_hass(self):
        if self._unsub:
            self._unsub()

    def _handle_notify(self, ntf_type, data):
        """Handle notify messages for Light."""
        _LOGGER.debug("ThermexLight._handle_notify: ntf_type=%s data=%s", ntf_type, data)
        if ntf_type.lower() != "light":
            return
        light = data.get("Light", {})
        self._is_on = bool(light.get("lightonoff", 0))
        self._brightness = light.get("lightbrightness", 0)
        # Thread-safe state update
        self.schedule_update_ha_state()

    async def async_turn_on(self, **kwargs):
        brightness = kwargs.get(ATTR_BRIGHTNESS, self._brightness)
        await self._hub.send_request(
            "update", {"Light": {"lightonoff": 1, "lightbrightness": brightness}}
        )
        # Optimistic update
        self._is_on = True
        self._brightness = brightness
        self.schedule_update_ha_state()

    async def async_turn_off(self, **kwargs):
        await self._hub.send_request(
            "update", {"Light": {"lightonoff": 0, "lightbrightness": 0}}
        )
        # Optimistic update
        self._is_on = False
        self._brightness = 0
        self.schedule_update_ha_state()

class ThermexDecoLight(LightEntity):
    """Decorative RGB light actuator."""
    _attr_name = "Thermex Deco Light"
    _attr_supported_color_modes = {ColorMode.HS, ColorMode.BRIGHTNESS}
    _attr_color_mode = ColorMode.HS

    def __init__(self, hub: ThermexHub):
        self._hub = hub
        self._attr_unique_id = f"{hub.unique_id}_light"
        self._is_on = False
        self._brightness = 0
        self._hs_color = (0, 0)
        self._unsub = None

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self._hub.unique_id)},
            manufacturer="Thermex",
            name=f"Thermex Hood ({self._hub._host})",
            model="ESP-API",
        )

    @property
    def is_on(self) -> bool:
        return self._is_on

    @property
    def brightness(self) -> int:
        return self._brightness

    @property
    def hs_color(self) -> tuple[float, float]:
        return self._hs_color

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self._hub._unique_id)},
            manufacturer="Thermex",
            name=f"Thermex Hood ({self._hub._host})",
            model="ESP-API",
        )

    async def async_added_to_hass(self):
        # Early subscribe
        self._unsub = async_dispatcher_connect(
            self.hass, THERMEX_NOTIFY, self._handle_notify
        )

        # Fetch initial state
        try:
            status = await self._hub.send_request("status", {})
            deco = status.get("Data", {}).get("Decolight", {})
            self._is_on = bool(deco.get("decolightonoff", 0))
            self._brightness = deco.get("decolightbrightness", 0)
            r = deco.get("decolightr", 0)
            g = deco.get("decolightg", 0)
            b = deco.get("decolightb", 0)
            self._hs_color = color_RGB_to_hs(r, g, b)
        except asyncio.TimeoutError:
            _LOGGER.warning(
                "ThermexDecoLight: initial STATUS timed out, deferring state until notify"
            )
        except Exception as err:
            _LOGGER.error("ThermexDecoLight: error fetching initial STATUS: %s", err)

    async def async_will_remove_from_hass(self):
        if self._unsub:
            self._unsub()

    def _handle_notify(self, ntf_type, data):
        _LOGGER.debug("ThermexDecoLight._handle_notify: ntf_type=%s data=%s", ntf_type, data)
        if ntf_type.lower() != "decolight":
            return
        deco = data.get("Decolight", {})
        self._is_on = bool(deco.get("decolightonoff", 0))
        self._brightness = deco.get("decolightbrightness", 0)
        r = deco.get("decolightr", 0)
        g = deco.get("decolightg", 0)
        b = deco.get("decolightb", 0)
        self._hs_color = color_RGB_to_hs(r, g, b)
        self.schedule_update_ha_state()

    async def async_turn_on(self, **kwargs):
        brightness = kwargs.get(ATTR_BRIGHTNESS, self._brightness)
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
        await self._hub.send_request("update", {"Decolight": payload})
        # Optimistic update
        self._is_on = True
        self._brightness = brightness
        self._hs_color = color_RGB_to_hs(r, g, b)
        self.schedule_update_ha_state()

    async def async_turn_off(self, **kwargs):
        await self._hub.send_request(
            "update", {"Decolight": {"decolightonoff": 0, "decolightbrightness": 0}}
        )
        # Optimistic update
        self._is_on = False
        self._brightness = 0
        self.schedule_update_ha_state()
