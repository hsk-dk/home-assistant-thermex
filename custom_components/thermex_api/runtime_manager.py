# custom_components/thermex_api/runtime_manager.py
import logging
from datetime import datetime
from homeassistant.util.dt import utcnow

_LOGGER = logging.getLogger(__name__)

class RuntimeManager:
    def __init__(self, store, hub):
        self._store = store
        self._hub = hub
        self._data = {}

    async def load(self):
        self._data = await self._store.async_load() or {}

    async def save(self):
        await self._store.async_save(self._data)

    def start(self):
        self._data["last_start"] = datetime.utcnow().timestamp()

    def stop(self):
        now = datetime.utcnow().timestamp()
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
            current_session = (datetime.utcnow().timestamp() - last_start) / 3600.0
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
