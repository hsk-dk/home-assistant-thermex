"""Fixtures for Thermex API integration tests."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import asyncio

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
    hub.get_coordinator_data = MagicMock(return_value={
        "connection_state": "connected",
        "last_error": None,
        "watchdog_active": False,
        "time_since_activity": 0,
        "heartbeat_interval": 30,
        "connection_timeout": 120,
    })
    hub.protocol_version = "1.0"
    hub.is_connected = True
    hub.startup_complete = True
    return hub


@pytest.fixture
def mock_store():
    """Create a mock Store."""
    store = MagicMock()
    store.async_save = AsyncMock()
    store.async_load = AsyncMock(return_value=None)
    return store


@pytest.fixture
def event_loop():
    """Create an event loop for async tests."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def mock_hass(event_loop):
    """Create a mock HomeAssistant instance with proper loop."""
    hass = MagicMock()
    hass.data = {}
    hass.states = MagicMock()
    hass.config_entries = MagicMock()
    hass.loop = event_loop
    hass.async_create_task = MagicMock(side_effect=lambda coro, name=None: asyncio.create_task(coro))
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
