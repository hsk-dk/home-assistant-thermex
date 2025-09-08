#!/usr/bin/env python3
"""
Debug script to test the delayed turn-off functionality.
This script helps verify the basic logic without Home Assistant.
"""

import asyncio
from datetime import datetime, timedelta
import logging

# Set up logging
logging.basicConfig(level=logging.DEBUG)
_LOGGER = logging.getLogger(__name__)

class MockDelayedTurnOff:
    """Mock class to test delayed turn-off logic."""
    
    def __init__(self):
        self._delayed_off_active = False
        self._delayed_off_remaining = 0
        self._delayed_off_scheduled_time = None
        self._delayed_off_handle = None
        self._is_on = True  # Simulate fan being on
        
    async def start_delayed_off(self):
        """Start the delayed turn-off timer."""
        _LOGGER.info("start_delayed_off called")
        
        if not self._is_on:
            _LOGGER.warning("Cannot start delayed turn-off: fan is not running")
            return

        # Cancel any existing delayed turn-off
        await self.cancel_delayed_off()

        # Use 2 minutes for testing (120 seconds)
        delay_minutes = 2
        
        _LOGGER.info("DEBUG: Using %d minutes for delayed turn-off", delay_minutes)
        
        self._delayed_off_active = True
        self._delayed_off_remaining = delay_minutes
        
        # Calculate scheduled time
        self._delayed_off_scheduled_time = datetime.now() + timedelta(minutes=delay_minutes)

        _LOGGER.info("Starting delayed turn-off: %d minutes (until %s)", 
                    delay_minutes, self._delayed_off_scheduled_time.strftime("%H:%M"))
        _LOGGER.debug("Delayed turn-off details: active=%s, remaining=%d", 
                     self._delayed_off_active, self._delayed_off_remaining)
        
        # Schedule the turn-off (using asyncio.call_later instead of HA's async_call_later)
        loop = asyncio.get_event_loop()
        self._delayed_off_handle = loop.call_later(delay_minutes * 60, self._handle_delayed_off_sync)
        
        _LOGGER.debug("Delayed turn-off scheduled: handle=%s, seconds=%d", 
                     self._delayed_off_handle is not None, delay_minutes * 60)
        
        # Start countdown timer (update every 30 seconds for testing)
        loop.call_later(30, self._update_countdown_sync)
        
    def _handle_delayed_off_sync(self):
        """Sync wrapper for delayed turn-off."""
        asyncio.create_task(self._handle_delayed_off())
        
    def _update_countdown_sync(self):
        """Sync wrapper for countdown update."""
        self._update_countdown()
        
    async def _handle_delayed_off(self):
        """Handle the delayed turn-off event."""
        _LOGGER.info("Executing delayed turn-off - fan should turn off now")
        _LOGGER.debug("Current fan state before turn-off: is_on=%s", self._is_on)
        
        # Clear delayed turn-off state first
        self._delayed_off_handle = None
        self._delayed_off_active = False
        self._delayed_off_remaining = 0
        self._delayed_off_scheduled_time = None
        
        # Turn off the fan
        await self.async_turn_off()
        
        _LOGGER.debug("Fan state after turn-off command: is_on=%s", self._is_on)
        _LOGGER.info("Delayed turn-off completed and state cleared")
        
    async def async_turn_off(self):
        """Mock turn off method."""
        _LOGGER.info("Turning off fan")
        self._is_on = False
        
    async def cancel_delayed_off(self):
        """Cancel the delayed turn-off timer."""
        if self._delayed_off_handle:
            _LOGGER.info("Cancelling existing delayed turn-off")
            self._delayed_off_handle.cancel()
            self._delayed_off_handle = None
        self._delayed_off_active = False
        self._delayed_off_remaining = 0
        self._delayed_off_scheduled_time = None
        
    def _update_countdown(self):
        """Update the countdown timer."""
        if self._delayed_off_active and self._delayed_off_remaining > 0:
            self._delayed_off_remaining = max(0, self._delayed_off_remaining - 0.5)  # 30 seconds = 0.5 minutes
            _LOGGER.info("Delayed turn-off countdown: %d minutes remaining", int(self._delayed_off_remaining))
            
            if self._delayed_off_remaining > 0:
                # Schedule next update in 30 seconds
                loop = asyncio.get_event_loop()
                loop.call_later(30, self._update_countdown_sync)

async def main():
    """Test the delayed turn-off functionality."""
    _LOGGER.info("Starting delayed turn-off test")
    
    mock_fan = MockDelayedTurnOff()
    
    # Start delayed turn-off
    await mock_fan.start_delayed_off()
    
    _LOGGER.info("Test started - waiting for delayed turn-off...")
    _LOGGER.info("Fan is currently: %s", "ON" if mock_fan._is_on else "OFF")
    _LOGGER.info("Scheduled time: %s", mock_fan._delayed_off_scheduled_time)
    
    # Wait longer than the delay to see if it works
    await asyncio.sleep(150)  # Wait 2.5 minutes
    
    _LOGGER.info("Test completed - fan is now: %s", "ON" if mock_fan._is_on else "OFF")

if __name__ == "__main__":
    asyncio.run(main())
