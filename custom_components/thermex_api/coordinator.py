"""Coordinator: the single place that holds the hood's state and the runtime counter."""
from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DOMAIN
from .delayed_off import DelayedOffManager
from .hub import ThermexHub
from .runtime_manager import RuntimeManager
from .state import PRESET_BY_SPEED, FanState, ThermexState, merge_status

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry

_LOGGER = logging.getLogger(__name__)


class ThermexCoordinator(DataUpdateCoordinator[ThermexState]):
    """Push-based: the hub hands over every Status/Notify, nothing is polled.

    The first refresh asks the hood for its full state, so entities always have
    data when they are added. The runtime counter is kept here (not in the fan
    entity), so it works whichever entities the user has enabled.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        hub: ThermexHub,
        runtime_manager: RuntimeManager,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{DOMAIN} {entry.entry_id}",
            update_interval=None,
        )
        self.hub = hub
        self.runtime_manager = runtime_manager
        self.delayed_off = DelayedOffManager(
            hass, lambda: entry.options, hub, runtime_manager, lambda: self.fan_running
        )
        self._fan_session_open = False
        entry.async_on_unload(async_dispatcher_connect(hass, hub.signal, self._handle_status))
        entry.async_on_unload(self.delayed_off.shutdown)

    @property
    def fan_running(self) -> bool:
        """Whether the fan is running right now."""
        return bool(self.data and self.data.fan and self.data.fan.running)

    async def _async_update_data(self) -> ThermexState:
        """Ask the hood for its full state."""
        try:
            resp = await self.hub.send_request("status", {})
        except (ConnectionError, TimeoutError) as err:
            raise UpdateFailed(
                translation_domain=DOMAIN,
                translation_key="cannot_connect",
                translation_placeholders={"host": self.hub.host},
            ) from err
        state = merge_status(self.data or ThermexState(), resp.get("Data") or {})
        self._track_runtime(state.fan)
        return state

    @callback
    def _handle_status(self, data: Mapping[str, Any]) -> None:
        """A Status or Notify arrived from the hood."""
        state = merge_status(self.data or ThermexState(), data)
        self._track_runtime(state.fan)
        self.async_set_updated_data(state)

    @callback
    def _track_runtime(self, fan: FanState | None) -> None:
        """Count the fan's running time and remember the level in use."""
        if fan is None:
            return
        runtime = self.runtime_manager
        changed = False

        if fan.running and not self._fan_session_open:
            runtime.start()
            changed = True
        elif not fan.running and self._fan_session_open:
            runtime.stop()
            changed = True
            # Switched off (also by the remote or the app): nothing left to delay
            self.delayed_off.cancel_soon()
        self._fan_session_open = fan.running

        if fan.running and runtime.get_last_reset() is None:
            runtime.reset()
            runtime.start()
            changed = True

        preset = PRESET_BY_SPEED.get(fan.speed)
        if fan.running and preset and preset != runtime.get_last_preset():
            runtime.set_last_preset(preset)
            changed = True

        if changed:
            self.hass.async_create_task(runtime.save())

    async def async_reset_runtime(self) -> None:
        """Reset the filter counter (a running fan keeps being counted)."""
        self.runtime_manager.reset()
        if self._fan_session_open:
            self.runtime_manager.start()
        await self.runtime_manager.save()
        self.async_update_listeners()
