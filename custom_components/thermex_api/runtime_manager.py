# custom_components/thermex_api/runtime_manager.py
import logging
from homeassistant.util.dt import utcnow

_LOGGER = logging.getLogger(__name__)

class RuntimeManager:
    def __init__(self, store, hub):
        self._store = store
        self._hub = hub
        self._data = {}

    async def load(self):
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
            if last_reset is not None:
                if isinstance(last_reset, str):
                    validated_data["last_reset"] = last_reset
                else:
                    _LOGGER.warning("Invalid last_reset format, ignoring")
            
            # Validate last_preset (should be string or None)
            last_preset = data.get("last_preset")
            if last_preset is not None:
                if isinstance(last_preset, str):
                    validated_data["last_preset"] = last_preset
                else:
                    _LOGGER.warning("Invalid last_preset format, ignoring")
            
            self._data = validated_data
            _LOGGER.debug("Runtime data loaded and validated successfully")
            
        except Exception as err:
            _LOGGER.error("Failed to load runtime data: %s. Starting fresh.", err)
            self._data = {}

    async def save(self):
        await self._store.async_save(self._data)

    def start(self):
        self._data["last_start"] = utcnow().timestamp()

    def stop(self):
        now = utcnow().timestamp()
        last_start = self._data.get("last_start")
        if last_start:
            run = now - last_start
            self._data["runtime_hours"] = self._data.get("runtime_hours", 0.0) + run / 3600.0
            self._data["last_start"] = None

    def reset(self):
        _LOGGER.info("Thermex filter time counter has been reset to 0.")
        self._data["runtime_hours"] = 0.0
        self._data["last_reset"] = utcnow().isoformat()
        self._data["last_start"] = None

    def get_runtime_hours(self):
        """Get total runtime hours, including current session if fan is running."""
        total_hours = self._data.get("runtime_hours", 0.0)
        
        # If fan is currently running, add current session time
        last_start = self._data.get("last_start")
        if last_start:
            current_session = (utcnow().timestamp() - last_start) / 3600.0
            total_hours += current_session
            
        return round(total_hours, 2)

    def get_last_reset(self):
        return self._data.get("last_reset")

    def get_days_since_reset(self):
        """Get number of days since last filter reset."""
        last_reset = self._data.get("last_reset")
        if not last_reset:
            return None
        
        try:
            reset_time = datetime.fromisoformat(last_reset.replace("Z", "+00:00"))
            now = utcnow()
            days_diff = (now - reset_time).days
            return days_diff
        except (ValueError, AttributeError) as e:
            _LOGGER.warning("Error calculating days since reset: %s", e)
            return None

    def get_filter_time(self):
        # For clarity: filter time is always runtime hours
        return self.get_runtime_hours()
    
    def get_last_preset(self):
        return self._data.get("last_preset", "off")

    def set_last_preset(self, mode):
        self._data["last_preset"] = mode
