"""Thermex Fan entity with discrete presets and persistent runtime tracking."""
import asyncio
import logging
from datetime import datetime, timedelta

from homeassistant.components.fan import FanEntity, FanEntityFeature
from homeassistant.core import callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers import entity_platform
from homeassistant.helpers.storage import Store
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.util.dt import utcnow
from homeassistant.helpers.event import async_call_later


from .hub import ThermexHub
from .const import DOMAIN, THERMEX_NOTIFY, STORAGE_VERSION, STORAGE_KEY, RUNTIME_STORAGE_FILE

_LOGGER = logging.getLogger(__name__)

# Preset names in the UI, mapped to the numeric API values
PRESET_MODES = ["off", "low", "medium", "high", "boost"]
_MODE_TO_VALUE = {"off": 0, "low": 1, "medium": 2, "high": 3, "boost": 4}
_VALUE_TO_MODE = {v: k for k, v in _MODE_TO_VALUE.items()}

async def async_setup_entry(hass, entry, async_add_entities):
    """Set up the Thermex fan with runtime storage."""
    hub: ThermexHub = hass.data[DOMAIN][entry.entry_id]
    store = Store(hass, STORAGE_VERSION,RUNTIME_STORAGE_FILE.format(entry_id=entry.entry_id))
    data = await store.async_load() or {}
    async_add_entities([ThermexFan(hub, store, data, entry.options)], update_before_add=True)

    # register a service so users can call thermost_api.reset_runtime
    platform = entity_platform.async_get_current_platform()
    platform.async_register_entity_service(
        "reset_runtime",    # service name: thermost_api.reset_runtime
        {},                 # no extra service schema
        "async_reset"       # method to call on the entity
    )

class ThermexFan(FanEntity):
    """Thermex extractor fan with presets and runtime tracking."""

    _attr_name = "Thermex Fan"
    # Show presets + on/off buttons, no slider
    _attr_supported_features = (
        FanEntityFeature.PRESET_MODE
        | FanEntityFeature.TURN_ON
        | FanEntityFeature.TURN_OFF
    )
    _attr_preset_modes = PRESET_MODES

    def __init__(self, hub: ThermexHub, store: Store, data: dict, options: dict):
        self._hub = hub
        self._store = store
        self._data = data
        self._options = options
        self._auto_off_handle = None


        # persistent state
        self._is_on = False
        self._preset_mode = data.get("last_preset", "off")
        self._runtime = data.get("runtime_hours", 0.0)
        self._last_start = data.get("last_start")  # timestamp float or None
        self._last_reset = data.get("last_reset")  # ISO timestamp str or None

        # Device info / unique ID
        self._attr_unique_id = f"{hub.unique_id}_fan"
        self._attr_icon = "mdi:fan"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, hub.unique_id)},
            manufacturer="Thermex",
            name=f"Thermex Hood ({hub._host})",
            model="ESP-API",
        )
        self._unsub = None

    @property
    def is_on(self) -> bool:
        return self._is_on

    @property
    def preset_mode(self) -> str | None:
        return self._preset_mode

    @property
    def extra_state_attributes(self) -> dict:
        return {
            "runtime_hours": round(self._runtime, 2),
            "last_start": self._last_start or "unknown",
            "last_reset": self._last_reset or "never",
            "threshold": self._options.get("runtime_threshold", 30),
            "alert": self._runtime >= self._options.get("runtime_threshold", 30),
        }

    async def async_added_to_hass(self):
        """Subscribe to hub notifications and fetch initial state."""
        self._unsub = async_dispatcher_connect(
            self.hass, THERMEX_NOTIFY, self._handle_notify
        )

        try:
            resp = await self._hub.send_request("Status", {})
            fan = resp.get("Data", {}).get("Fan", {})
            speed = fan.get("fanspeed", 0)
            on = bool(fan.get("fanonoff", 0)) and speed != 0
            self._is_on = on
            self._preset_mode = _VALUE_TO_MODE.get(speed, "off")
        except asyncio.TimeoutError:
            _LOGGER.warning("ThermexFan: initial STATUS timed out")
        except Exception as err:
            _LOGGER.error("ThermexFan: error fetching initial STATUS: %s", err)

    async def async_will_remove_from_hass(self):
        """Unsubscribe on removal."""
        if self._unsub:
            self._unsub()

    @callback
    def _handle_notify(self, ntf_type: str, data: dict) -> None:
        """Handle incoming fan notifications and update runtime/state."""
        if ntf_type.lower() != "fan":
            return

        fan = data.get("Fan", {})
        new_speed = fan.get("fanspeed", 0)
        new_on = bool(fan.get("fanonoff", 0)) and new_speed != 0
        new_mode = _VALUE_TO_MODE.get(new_speed, "off")

        now = datetime.utcnow().timestamp()

        # turned on?
        if new_on and not self._is_on:
            self._last_start = now
            self._data["last_start"] = now

        # turned off?
        if not new_on and self._is_on and self._last_start:
            run = now - float(self._last_start)
            self._runtime += run / 3600.0
            self._data["runtime_hours"] = self._runtime
            self._last_start = None
            self._data["last_start"] = None

        # always record last_reset on first on
        if new_on and self._last_reset is None:
            iso = utcnow().isoformat()
            self._last_reset = iso
            self._data["last_reset"] = iso

        # update
        self._is_on = new_on
        self._preset_mode = new_mode

        # persist storage
        self.hass.async_create_task(self._store.async_save(self._data))

        # update entity
        self.schedule_update_ha_state()

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        """Switch API on/off with speed, let _handle_notify do the rest."""
        speed = _MODE_TO_VALUE[preset_mode]
        await self._hub.send_request("Update", {"Fan": {"fanonoff": int(speed > 0), "fanspeed": speed}})

    async def async_turn_on(self, percentage=None, preset_mode=None, **kwargs) -> None:
        """Turn on via preset (or last known)."""
        # decide which speed to send
        if preset_mode:
            mode = preset_mode
        elif self._preset_mode and self._preset_mode != "off":
            mode = self._preset_mode
        else:
            mode = "medium"

        # Cancel previous timer if it exists
        #if self._auto_off_handle:
        #    self._auto_off_handle()
        #    self._auto_off_handle = None

        # Read the setting from config entry options
        #auto_off_minutes = self._config_entry.options.get("fan_auto_off_minutes", 10)

        # Schedule turn off
        #self._auto_off_handle = async_call_later(
        #    self.hass,
        #    timedelta(minutes=auto_off_minutes),
        #    self._handle_auto_off
        #)

        # actually send the API command
        await self.async_set_preset_mode(mode)
        # ——— START YOUR RUNTIME CLOCK ———
        now_ts = datetime.utcnow().timestamp()
        if not self._last_start:
            self._last_start = now_ts
            self._data["last_start"] = now_ts
        if self._last_reset is None:
            iso = utcnow().isoformat()
            self._last_reset = iso
            self._data["last_reset"] = iso 
        # ——— OPTIMISTIC STATE UPDATE ———
        self._is_on = True
        self._preset_mode = mode
        self._data["last_preset"] = mode
        self.hass.async_create_task(self._store.async_save(self._data))
        self.schedule_update_ha_state()

    async def async_turn_off(self, **kwargs) -> None:
        """Turn off."""
        await self.async_set_preset_mode("off")
        # ——— OPTIMISTIC STATE UPDATE ———
        self._is_on = False
        self._preset_mode = "off"
        self._data["last_preset"] = "off"
        self.hass.async_create_task(self._store.async_save(self._data))
        self.schedule_update_ha_state()

    async def async_reset(self, **kwargs) -> None:
        """Reset the runtime counter."""
        self._runtime = 0.0
        self._last_start = None
        self._last_reset = utcnow().isoformat()
        self._data.update({
            "runtime_hours": self._runtime,
            "last_start": None,
            "last_reset": self._last_reset,
        })
        await self._store.async_save(self._data)
        self.schedule_update_ha_state()

    async def _handle_auto_off(self, _now):
        self._auto_off_handle = None
        _LOGGER.info("Auto turning off fan after timeout")
        await self.async_turn_off()
        self.async_write_ha_state()
