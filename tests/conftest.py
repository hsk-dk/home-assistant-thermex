"""Fixtures for Thermex API integration tests."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from custom_components.thermex_api.const import DOMAIN


@pytest.fixture
def mock_hub():
    """Create a mock ThermexHub."""
    hub = MagicMock()
    hub.unique_id = "test_thermex_hub"
    hub.device_info = {
        "identifiers": {(DOMAIN, "test_thermex_hub")},
        "name": "Test Thermex Hood",
        "manufacturer": "Thermex",
        "model": "Test Model",
    }
    hub.send_request = AsyncMock()
    hub.get_coordinator_data = MagicMock(return_value={})
    hub.startup_complete = True
    return hub


@pytest.fixture
def mock_store():
    """Create a mock Store."""
    store = MagicMock(spec=Store)
    store.async_save = AsyncMock()
    store.async_load = AsyncMock(return_value=None)
    return store


@pytest.fixture
async def mock_hass():
    """Create a mock HomeAssistant instance."""
    hass = MagicMock(spec=HomeAssistant)
    hass.data = {}
    hass.states = MagicMock()
    hass.config_entries = MagicMock()
    return hass


@pytest.fixture
def mock_config_entry():
    """Create a mock ConfigEntry."""
    entry = MagicMock()
    entry.entry_id = "test_entry_id"
    entry.data = {
        "host": "192.168.1.100",
        "api_key": "test_api_key",
    }
    entry.options = {
        "fan_alert_hours": 100,
        "fan_alert_days": 90,
        "fan_auto_off_delay": 60,
        "enable_decolight": False,
    }
    return entry
