"""The delayed turn-off of the fan: a timer that survives reloads and restarts."""
from __future__ import annotations

import logging
import math
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers.event import async_call_later
from homeassistant.util import dt as dt_util

from .const import DELAYED_TURNOFF_COUNTDOWN_INTERVAL, DOMAIN

if TYPE_CHECKING:
    from .hub import ThermexHub
    from .runtime_manager import RuntimeManager

_LOGGER = logging.getLogger(__name__)


class DelayedOffManager:
    """Turns the fan off after the configured delay.

    The due time is stored, so the timer is resumed after a reload or restart (one
    that came due while Home Assistant was down is dropped). Entities listen for
    changes with `async_add_listener`.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        options: Callable[[], dict],
        hub: ThermexHub,
        runtime_manager: RuntimeManager,
        fan_running: Callable[[], bool],
    ) -> None:
        self._hass = hass
        self._options = options
        self._hub = hub
        self._runtime_manager = runtime_manager
        self._fan_running = fan_running
        self._listeners: list[Callable[[], None]] = []
        self._off_handle: Callable[[], None] | None = None
        self._countdown_handle: Callable[[], None] | None = None
        self.active = False
        self.remaining = 0  # whole minutes left
        self.scheduled_time: datetime | None = None

    @property
    def delay_minutes(self) -> int:
        """The configured delay, kept within what the options allow."""
        return max(1, min(120, self._options().get("fan_auto_off_delay", 10)))

    @callback
    def async_add_listener(self, update: Callable[[], None]) -> Callable[[], None]:
        """Call `update` whenever the timer changes; returns the unsubscribe function."""
        self._listeners.append(update)

        @callback
        def remove() -> None:
            if update in self._listeners:
                self._listeners.remove(update)

        return remove

    @callback
    def _notify(self) -> None:
        for update in list(self._listeners):
            update()

    async def async_start(self) -> None:
        """Start the timer (restarting a running one)."""
        if not self._fan_running():
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="fan_not_running",
            )
        await self.async_cancel()

        scheduled = dt_util.now() + timedelta(minutes=self.delay_minutes)
        _LOGGER.info(
            "Starting delayed turn-off: %d minutes (until %s)",
            self.delay_minutes,
            scheduled.strftime("%H:%M"),
        )
        # Remember it, so a reload or restart does not silently drop the timer
        self._runtime_manager.set_delayed_off(scheduled)
        await self._runtime_manager.save()
        self._arm(scheduled)
        self._notify()

    async def async_cancel(self) -> None:
        """Cancel the timer."""
        self._cancel_timers()
        had_saved = self._runtime_manager.get_delayed_off() is not None
        if had_saved:
            self._runtime_manager.set_delayed_off(None)
            await self._runtime_manager.save()

        if self.active or had_saved:
            _LOGGER.info("Delayed turn-off cancelled")
        self.active = False
        self.remaining = 0
        self.scheduled_time = None
        self._notify()

    @callback
    def cancel_soon(self) -> None:
        """Cancel from a callback (the fan was switched off by other means)."""
        if self.active:
            self._hass.async_create_task(self.async_cancel())

    @callback
    def restore(self) -> None:
        """Resume a timer that was pending before a reload or restart."""
        due = self._runtime_manager.get_delayed_off()
        if due is None:
            return
        if due > dt_util.now():
            self._arm(due)
        else:
            self._runtime_manager.set_delayed_off(None)
            self._hass.async_create_task(self._runtime_manager.save())

    @callback
    def shutdown(self) -> None:
        """Stop the timers; a pending turn-off stays saved for the next load."""
        self._cancel_timers()

    @callback
    def _arm(self, scheduled: datetime) -> None:
        """Schedule the turn-off (and the minute countdown) for the given time."""
        seconds = max(0.0, (scheduled - dt_util.now()).total_seconds())
        self.active = True
        self.remaining = max(1, math.ceil(seconds / 60))
        self.scheduled_time = scheduled
        self._off_handle = async_call_later(self._hass, seconds, self._due)
        self._countdown_handle = async_call_later(
            self._hass, DELAYED_TURNOFF_COUNTDOWN_INTERVAL, self._tick
        )

    @callback
    def _cancel_timers(self) -> None:
        if self._off_handle:
            self._off_handle()
            self._off_handle = None
        # Also stop the countdown chain, otherwise a later restart runs two of them
        if self._countdown_handle:
            self._countdown_handle()
            self._countdown_handle = None

    @callback
    def _tick(self, _now: datetime | None = None) -> None:
        """Count down one minute."""
        self._countdown_handle = None
        if not self.active or self.remaining <= 0:
            return
        self.remaining -= 1
        self._notify()
        if self.remaining > 0:
            self._countdown_handle = async_call_later(
                self._hass, DELAYED_TURNOFF_COUNTDOWN_INTERVAL, self._tick
            )

    async def _due(self, _now: datetime) -> None:
        """The delay has passed: turn the fan off."""
        _LOGGER.info("Executing delayed turn-off")
        self._off_handle = None
        await self.async_cancel()
        try:
            await self._hub.send_update({"Fan": {"fanonoff": 0, "fanspeed": 0}})
        except HomeAssistantError as err:
            _LOGGER.error("Delayed turn-off failed: %s", err)
