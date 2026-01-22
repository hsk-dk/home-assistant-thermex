# custom_components/thermex_api/runtime_manager.py
import logging
from datetime import datetime
from typing import Any

from homeassistant.helpers.storage import Store
from homeassistant.util.dt import utcnow, parse_datetime

_LOGGER = logging.getLogger(__name__)

class RuntimeManager:
    """Manages persistent runtime tracking for the Thermex fan."""
    
    def __init__(self, store: Store, hub: Any) -> None:
        self._store = store
        self._hub = hub
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
            
            # Validate last_start (should be float timestamp or None)
            last_start = data.get("last_start")
            if last_start is not None:
                try:
                    validated_data["last_start"] = float(last_start)
                except (ValueError, TypeError):
                    _LOGGER.warning("Invalid last_start timestamp, ignoring")
            
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
    
    def get_last_preset(self) -> str:
        """Get the last preset mode used."""
        return self._data.get("last_preset", "off")

    def set_last_preset(self, mode: str) -> None:
        """Set the last preset mode."""
        self._data["last_preset"] = mode
