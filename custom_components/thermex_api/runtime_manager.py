# custom_components/thermex_api/runtime_manager.py
import logging
from datetime import datetime
from typing import Any

from homeassistant.helpers.storage import Store
from homeassistant.util.dt import parse_datetime, utcnow

_LOGGER = logging.getLogger(__name__)

class RuntimeManager:
    """Manages persistent runtime tracking for the Thermex fan."""
    
    def __init__(self, store: Store) -> None:
        self._store = store
        self._data: dict[str, Any] = {}

    async def load(self) -> None:
        """Load runtime data from storage with validation."""
        try:
            data = await self._store.async_load()
            if data is None:
                self._data = {}
                _LOGGER.debug("No existing runtime data found, starting fresh")
                return
            
            # Validate that loaded data is a dictionary
            if not isinstance(data, dict):
                _LOGGER.warning(
                    "Corrupted runtime data (not a dict): %s. Starting fresh.",
                    type(data).__name__
                )
                self._data = {}
                return
            
            # Validate and sanitize data types
            validated_data = {}
            
            # Validate runtime_hours (should be float >= 0)
            runtime_hours = data.get("runtime_hours")
            if runtime_hours is not None:
                try:
                    runtime_hours = float(runtime_hours)
                    if runtime_hours >= 0:
                        validated_data["runtime_hours"] = runtime_hours
                    else:
                        _LOGGER.warning("Invalid runtime_hours (negative), resetting to 0")
                        validated_data["runtime_hours"] = 0.0
                except (ValueError, TypeError):
                    _LOGGER.warning("Invalid runtime_hours type, resetting to 0")
                    validated_data["runtime_hours"] = 0.0
            
            # last_start is deliberately NOT restored: a session that was open when
            # HA stopped would otherwise count all the downtime as fan runtime.
            # If the fan is still running, the first status notify starts a new session.
            
            # Validate last_reset (should be ISO format string or None)
            last_reset = data.get("last_reset")
            if last_reset is not None and isinstance(last_reset, str):
                validated_data["last_reset"] = last_reset
            elif last_reset is not None:
                _LOGGER.warning("Invalid last_reset format, ignoring")
            
            # Validate last_preset (should be string or None)
            last_preset = data.get("last_preset")
            if last_preset is not None and isinstance(last_preset, str):
                validated_data["last_preset"] = last_preset
            elif last_preset is not None:
                _LOGGER.warning("Invalid last_preset format, ignoring")
            
            # Pending delayed turn-off (ISO timestamp) so it survives a reload/restart
            delayed_off = data.get("delayed_off_at")
            if isinstance(delayed_off, str) and parse_datetime(delayed_off) is not None:
                validated_data["delayed_off_at"] = delayed_off
            elif delayed_off is not None:
                _LOGGER.warning("Invalid delayed_off_at, ignoring")

            self._data = validated_data
            _LOGGER.debug("Runtime data loaded and validated successfully")
            
        except Exception as err:
            _LOGGER.error("Failed to load runtime data: %s. Starting fresh.", err)
            self._data = {}

    async def save(self) -> None:
        """Save runtime data to persistent storage."""
        await self._store.async_save(self._data)

    def start(self) -> None:
        """Mark the start of a runtime session."""
        self._data["last_start"] = utcnow().timestamp()

    def stop(self) -> None:
        """Mark the end of a runtime session and update total hours."""
        now = utcnow().timestamp()
        last_start = self._data.get("last_start")
        if last_start:
            run = now - last_start
            self._data["runtime_hours"] = self._data.get("runtime_hours", 0.0) + run / 3600.0
            self._data["last_start"] = None

    def is_running(self) -> bool:
        """Whether a runtime session is currently open."""
        return bool(self._data.get("last_start"))

    def checkpoint(self) -> None:
        """Move the time of the open session into the total and keep the session open.

        Called regularly while the fan runs, and before shutdown, so that a restart
        or reload of Home Assistant never loses the session in progress.
        """
        last_start = self._data.get("last_start")
        if not last_start:
            return
        now = utcnow().timestamp()
        self._data["runtime_hours"] = self._data.get("runtime_hours", 0.0) + (now - last_start) / 3600.0
        self._data["last_start"] = now

    def reset(self) -> None:
        """Reset the runtime counter to zero."""
        _LOGGER.info("Thermex filter time counter has been reset to 0.")
        self._data["runtime_hours"] = 0.0
        self._data["last_reset"] = utcnow().isoformat()
        self._data["last_start"] = None

    def get_runtime_hours(self) -> float:
        """Get total runtime hours, including current session if fan is running."""
        total_hours = self._data.get("runtime_hours", 0.0)
        
        # If fan is currently running, add current session time
        last_start = self._data.get("last_start")
        if last_start:
            current_session = (utcnow().timestamp() - last_start) / 3600.0
            total_hours += current_session
            
        return round(total_hours, 2)

    def get_last_reset(self) -> str | None:
        """Get the ISO timestamp of the last reset."""
        return self._data.get("last_reset")

    def get_days_since_reset(self) -> int | None:
        """Get number of days since last filter reset."""
        last_reset = self._data.get("last_reset")
        if not last_reset:
            return None
        
        try:
            # Try using HA's parse_datetime first (handles various formats)
            reset_time = parse_datetime(last_reset)
            if reset_time is None:
                # Fallback to fromisoformat for strict ISO format
                reset_time = datetime.fromisoformat(last_reset.replace("Z", "+00:00"))
            
            now = utcnow()
            days_diff = (now - reset_time).days
            return days_diff
        except (ValueError, AttributeError, TypeError) as e:
            _LOGGER.warning("Error calculating days since reset: %s", e)
            return None

    def get_filter_time(self) -> float:
        """Get filter time (alias for runtime hours)."""
        # For clarity: filter time is always runtime hours
        return self.get_runtime_hours()
    
    def get_delayed_off(self) -> datetime | None:
        """Return when the pending delayed turn-off is due, if any."""
        value = self._data.get("delayed_off_at")
        return parse_datetime(value) if value else None

    def set_delayed_off(self, when: datetime | None) -> None:
        """Remember (or clear) the pending delayed turn-off."""
        if when is None:
            self._data.pop("delayed_off_at", None)
        else:
            self._data["delayed_off_at"] = when.isoformat()

    def get_last_preset(self) -> str:
        """Get the last preset mode used."""
        return self._data.get("last_preset", "off")

    def set_last_preset(self, mode: str) -> None:
        """Set the last preset mode."""
        self._data["last_preset"] = mode
