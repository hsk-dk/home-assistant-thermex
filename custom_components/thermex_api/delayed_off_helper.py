"""Helper class for managing delayed turn-off timer functionality."""
import logging
from datetime import datetime, timedelta
from typing import Optional, Callable, TYPE_CHECKING

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.event import async_call_later
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.util import dt as dt_util

from .const import THERMEX_NOTIFY, DELAYED_TURNOFF_COUNTDOWN_INTERVAL

if TYPE_CHECKING:
    from .fan import ThermexFan

_LOGGER = logging.getLogger(__name__)


class DelayedOffHelper:
    """Manages delayed turn-off timer for Thermex fan."""

    def __init__(self, hass: HomeAssistant, fan_entity: "ThermexFan") -> None:
        """Initialize the delayed off helper.
        
        Args:
            hass: Home Assistant instance
            fan_entity: Reference to the parent fan entity
        """
        self._hass = hass
        self._fan_entity = fan_entity
        
        # Timer state
        self._active = False
        self._remaining_minutes = 0
        self._scheduled_time: Optional[datetime] = None
        self._timer_handle: Optional[Callable[[], None]] = None
        self._countdown_handle: Optional[Callable[[], None]] = None

    @property
    def is_active(self) -> bool:
        """Return whether delayed turn-off is active."""
        return self._active

    @property
    def remaining_minutes(self) -> int:
        """Return remaining minutes until turn-off."""
        return self._remaining_minutes

    @property
    def scheduled_time(self) -> Optional[datetime]:
        """Return the scheduled turn-off time."""
        return self._scheduled_time

    def get_state_attributes(self) -> dict:
        """Return state attributes for the fan entity."""
        attributes = {
            "delayed_off_active": self._active,
            "delayed_off_remaining": self._remaining_minutes,
        }
        
        if self._scheduled_time:
            attributes["delayed_off_scheduled_time"] = self._scheduled_time.isoformat()
        
        return attributes

    async def start(self, delay_minutes: int) -> bool:
        """Start the delayed turn-off timer.
        
        Args:
            delay_minutes: Number of minutes until turn-off (1-120)
            
        Returns:
            True if started successfully, False otherwise
        """
        # Validate delay
        delay_minutes = max(1, min(120, delay_minutes))
        
        # Check if fan is running
        if not self._fan_entity.is_on:
            _LOGGER.warning("Cannot start delayed turn-off: fan is not running")
            return False

        # Cancel any existing timer
        await self.cancel()

        # Set up new timer
        self._active = True
        self._remaining_minutes = delay_minutes
        self._scheduled_time = dt_util.now() + timedelta(minutes=delay_minutes)

        scheduled_time_str = self._scheduled_time.strftime("%H:%M")
        _LOGGER.info(
            "Starting delayed turn-off: %d minutes (until %s)",
            delay_minutes,
            scheduled_time_str
        )
        
        # Schedule the actual turn-off
        self._timer_handle = async_call_later(
            self._hass,
            delay_minutes * 60,
            self._execute_turn_off
        )
        
        # Start the countdown timer (updates every minute)
        self._countdown_handle = async_call_later(
            self._hass,
            DELAYED_TURNOFF_COUNTDOWN_INTERVAL,
            self._update_countdown
        )
        
        # Notify other entities
        self._dispatch_state_change()
        
        return True

    async def cancel(self) -> None:
        """Cancel the delayed turn-off timer."""
        was_active = self._active
        
        # Cancel timers
        if self._timer_handle:
            self._timer_handle()
            self._timer_handle = None
        
        if self._countdown_handle:
            self._countdown_handle()
            self._countdown_handle = None

        # Clear state
        self._active = False
        self._remaining_minutes = 0
        self._scheduled_time = None
        
        if was_active:
            _LOGGER.info("Delayed turn-off cancelled")
            self._dispatch_state_change()

    @callback
    def _update_countdown(self, _now=None) -> None:
        """Update the countdown timer display."""
        if not self._active:
            return

        # Decrement the remaining time
        if self._remaining_minutes > 0:
            self._remaining_minutes -= 1
            
            # Trigger state update on fan entity
            self._fan_entity.schedule_update_ha_state()
            
            # Schedule next update if still active
            if self._remaining_minutes > 0:
                self._countdown_handle = async_call_later(
                    self._hass,
                    DELAYED_TURNOFF_COUNTDOWN_INTERVAL,
                    self._update_countdown
                )

    async def _execute_turn_off(self, _now) -> None:
        """Execute the delayed turn-off."""
        _LOGGER.info("Executing delayed turn-off - turning fan off now")
        _LOGGER.debug(
            "Current fan state before turn-off: is_on=%s, preset=%s",
            self._fan_entity.is_on,
            self._fan_entity.preset_mode
        )
        
        # Clear timer state
        self._timer_handle = None
        self._active = False
        self._remaining_minutes = 0
        self._scheduled_time = None
        
        # Turn off the fan
        await self._fan_entity.async_turn_off()
        
        _LOGGER.debug(
            "Fan state after turn-off command: is_on=%s, preset=%s",
            self._fan_entity.is_on,
            self._fan_entity.preset_mode
        )
        _LOGGER.info("Delayed turn-off completed")

    def _dispatch_state_change(self) -> None:
        """Dispatch state change notification to other entities."""
        scheduled_iso = self._scheduled_time.isoformat() if self._scheduled_time else None
        
        async_dispatcher_send(
            self._hass,
            THERMEX_NOTIFY,
            "delayed_turn_off",
            {
                "active": self._active,
                "scheduled_time": scheduled_iso,
                "remaining": self._remaining_minutes
            },
        )

    async def cleanup(self) -> None:
        """Clean up resources when entity is removed."""
        await self.cancel()
