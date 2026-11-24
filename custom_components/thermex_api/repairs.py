"""Repair issue: the hood has been unreachable for a long time."""
from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.event import async_call_later

from .const import DOMAIN, OFFLINE_ISSUE_DELAY

if TYPE_CHECKING:
    from .data import ThermexConfigEntry
    from .hub import ThermexHub


class OfflineIssue:
    """Raises a repair issue when the hood has been offline for a while, and clears it again.

    A hood that is switched off at the mains, or that is restarting, is back soon and needs
    no attention, so the issue only appears after OFFLINE_ISSUE_DELAY seconds. It tells the
    user what can be checked (power, Wi-Fi, the API setting, a new IP address) and goes away
    by itself as soon as the hood is connected again.
    """

    def __init__(self, hass: HomeAssistant, entry: ThermexConfigEntry, hub: ThermexHub) -> None:
        self._hass = hass
        self._hub = hub
        self._issue_id = f"hood_offline_{entry.entry_id}"
        self._timer: CALLBACK_TYPE | None = None
        self._raised = False
        entry.async_on_unload(
            async_dispatcher_connect(hass, hub.availability_signal, self._handle_availability)
        )
        entry.async_on_unload(self.shutdown)

    @callback
    def start(self) -> None:
        """Look at the current state (the hood may already be offline when this is set up)."""
        self._handle_availability()

    @callback
    def _handle_availability(self) -> None:
        if self._hub.available:
            self._clear()
        elif self._hub.connection_state != "closed" and self._timer is None and not self._raised:
            self._timer = async_call_later(self._hass, OFFLINE_ISSUE_DELAY, self._raise_issue)

    @callback
    def _raise_issue(self, _now: object) -> None:
        self._timer = None
        if self._hub.available:
            return
        self._raised = True
        ir.async_create_issue(
            self._hass,
            DOMAIN,
            self._issue_id,
            is_fixable=False,
            severity=ir.IssueSeverity.WARNING,
            translation_key="hood_offline",
            translation_placeholders={"host": self._hub.host},
        )

    @callback
    def _clear(self) -> None:
        if self._timer is not None:
            self._timer()
            self._timer = None
        if self._raised:
            self._raised = False
            ir.async_delete_issue(self._hass, DOMAIN, self._issue_id)

    @callback
    def shutdown(self) -> None:
        """Stop watching and remove the issue (the entry is unloaded or removed)."""
        self._clear()
