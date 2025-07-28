# File: custom_components/thermex_api/button.py
import logging
from homeassistant.components.button import ButtonEntity
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.storage import Store
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.util.dt import utcnow

from .const import DOMAIN, THERMEX_NOTIFY, STORAGE_VERSION, RUNTIME_STORAGE_FILE
from .hub import ThermexHub

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass, entry, async_add_entities):
    """Set up the Reset Filter Timer button for Thermex API."""
    hub: ThermexHub = hass.data[DOMAIN][entry.entry_id]
    store = Store(
        hass,
        STORAGE_VERSION,
        RUNTIME_STORAGE_FILE.format(entry_id=entry.entry_id),
    )

    async_add_entities([
        ResetFilterButton(hub, store, entry.entry_id),
    ])


class ResetFilterButton(ButtonEntity):
    """Button that resets the fan runtime (filter usage) counter."""

    def __init__(self, hub: ThermexHub, store: Store, entry_id: str):
        self._hub = hub
        self._store = store
        self._entry_id = entry_id

        self._attr_unique_id = f"{hub.unique_id}_reset_runtime"
        self._attr_name = "Reset Filter Timer"
        self._attr_icon = "mdi:refresh"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, hub.unique_id)},
            manufacturer="Thermex",
            name=f"Thermex Hood ({hub._host})",
            model="ESP-API",
        )

    async def async_press(self) -> None:
        """Handle the button press: reset runtime and filter time."""
        # Reset persistent runtime tracking (fan)
        data = await self._store.async_load() or {}
        reset_time = utcnow().isoformat()
        data.update({
            "runtime_hours": 0.0,
            "last_start": None,
            "last_reset": reset_time,
        })
        await self._store.async_save(data)
        _LOGGER.info("Thermex runtime has been reset: %s", data)

        # Reset global filtertime (hub)
        self._hub.reset_filter_time()
        _LOGGER.info("Thermex filter time counter has been reset to 0.")

        # Trigger fan + filter sensor updates
        async_dispatcher_send(
            self.hass,
            THERMEX_NOTIFY,
            "fan",
            {"Fan": {}},
        )

        # If you use a coordinator-based sensor (like filter time), force refresh
        coordinator = self.hass.data[DOMAIN].get("coordinator")
        if coordinator:
            await coordinator.async_request_refresh()
