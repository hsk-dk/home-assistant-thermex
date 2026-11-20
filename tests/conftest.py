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
    hub.send_update = AsyncMock()
    hub.signal = "thermex_api_notify_test"
    hub.availability_signal = "thermex_api_notify_availability_test"
    hub.available = True
    hub.protocol_version = "1.0"
    hub.host = "192.168.1.100"
    hub.connection_state = "connected"
    hub.last_error = None
    return hub


@pytest.fixture
def runtime_manager():
    """A RuntimeManager stand-in with plausible stored values."""
    rm = MagicMock()
    rm.get_runtime_hours = MagicMock(return_value=12.5)
    rm.get_filter_time = MagicMock(return_value=12.5)
    rm.get_days_since_reset = MagicMock(return_value=10)
    rm.get_last_reset = MagicMock(return_value="2026-01-15T10:00:00+00:00")
    rm.get_last_preset = MagicMock(return_value="off")
    rm.get_delayed_off = MagicMock(return_value=None)
    rm.save = AsyncMock()
    return rm


@pytest.fixture
def delayed_off():
    """A DelayedOffManager stand-in."""
    d = MagicMock()
    d.active = False
    d.remaining = 0
    d.scheduled_time = None
    d.delay_minutes = 60
    d.async_start = AsyncMock()
    d.async_cancel = AsyncMock()
    d.async_add_listener = MagicMock(return_value=MagicMock())
    return d


@pytest.fixture
def coordinator(mock_hub, mock_config_entry, runtime_manager, delayed_off):
    """A coordinator stand-in; tests set `coordinator.data` to the state they need."""
    from custom_components.thermex_api.state import ThermexState

    c = MagicMock()
    c.hub = mock_hub
    c.config_entry = mock_config_entry
    c.runtime_manager = runtime_manager
    c.delayed_off = delayed_off
    c.data = ThermexState()
    c.fan_running = False
    c.async_reset_runtime = AsyncMock()
    return c


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
    hass.states.get = MagicMock(return_value=None)
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
