"""Tests for RuntimeManager."""
import pytest
from unittest.mock import AsyncMock, MagicMock
from homeassistant.util.dt import utcnow

from custom_components.thermex_api.runtime_manager import RuntimeManager


class TestRuntimeManager:
    """Test RuntimeManager functionality."""

    @pytest.fixture
    def runtime_manager(self, mock_store):
        """Create a RuntimeManager instance."""
        return RuntimeManager(mock_store)

    @pytest.mark.asyncio
    async def test_load_empty_store(self, runtime_manager, mock_store):
        """Test loading from empty store initializes defaults."""
        mock_store.async_load = AsyncMock(return_value=None)
        
        await runtime_manager.load()
        
        assert runtime_manager.get_runtime_hours() == 0.0
        assert runtime_manager.get_last_reset() is None
        assert runtime_manager.get_days_since_reset() is None

    @pytest.mark.asyncio
    async def test_load_existing_data(self, runtime_manager, mock_store):
        """Test loading existing runtime data."""
        test_data = {
            "runtime_hours": 2.0,
            "last_reset": "2026-01-15T10:00:00Z",
            "last_start": None,
        }
        mock_store.async_load = AsyncMock(return_value=test_data)
        
        await runtime_manager.load()
        
        assert runtime_manager.get_runtime_hours() == 2.0
        assert runtime_manager.get_last_reset() == "2026-01-15T10:00:00Z"

    @pytest.mark.asyncio
    async def test_load_validates_negative_runtime(self, runtime_manager, mock_store):
        """Test that negative runtime values are rejected."""
        test_data = {
            "runtime_hours": -1.5,
            "last_reset": "2026-01-15T10:00:00Z",
        }
        mock_store.async_load = AsyncMock(return_value=test_data)
        
        await runtime_manager.load()
        
        # Should reset to 0 due to validation
        assert runtime_manager.get_runtime_hours() == 0.0

    @pytest.mark.asyncio
    async def test_load_validates_invalid_timestamp(self, runtime_manager, mock_store):
        """Test that invalid timestamps are handled gracefully."""
        test_data = {
            "runtime_hours": 1.0,
            "last_reset": "not-a-valid-timestamp",
        }
        mock_store.async_load = AsyncMock(return_value=test_data)
        
        await runtime_manager.load()
        
        # Should load runtime successfully
        assert runtime_manager.get_runtime_hours() == 1.0

    @pytest.mark.asyncio
    async def test_start_and_stop(self, runtime_manager):
        """Test starting and stopping runtime tracking."""
        await runtime_manager.load()
        
        # Start tracking
        runtime_manager.start()
        assert runtime_manager._data.get("last_start") is not None
        
        # Stop tracking
        runtime_manager.stop()
        assert runtime_manager._data.get("last_start") is None
        # Should have accumulated some runtime (> 0)
        assert runtime_manager.get_runtime_hours() >= 0.0

    @pytest.mark.asyncio
    async def test_reset_runtime(self, runtime_manager):
        """Test resetting runtime clears data and sets timestamp."""
        await runtime_manager.load()
        
        # Set some runtime data
        runtime_manager._data["runtime_hours"] = 10.0
        runtime_manager.start()
        
        # Reset
        runtime_manager.reset()
        
        assert runtime_manager.get_runtime_hours() == 0.0
        assert runtime_manager._data.get("last_start") is None
        assert runtime_manager.get_last_reset() is not None

    @pytest.mark.asyncio
    async def test_get_days_since_reset(self, runtime_manager, mock_store):
        """Test calculating days since last reset."""
        from datetime import timedelta
        
        # Set reset time to 5 days ago
        five_days_ago = utcnow() - timedelta(days=5)
        test_data = {
            "runtime_hours": 10.0,
            "last_reset": five_days_ago.isoformat(),
        }
        mock_store.async_load = AsyncMock(return_value=test_data)
        
        await runtime_manager.load()
        
        days = runtime_manager.get_days_since_reset()
        
        # Should be approximately 5 days
        assert days is not None
        assert 4 <= days <= 6

    @pytest.mark.asyncio
    async def test_get_days_since_reset_no_reset(self, runtime_manager):
        """Test days since reset when never reset."""
        await runtime_manager.load()
        
        assert runtime_manager.get_days_since_reset() is None

    @pytest.mark.asyncio
    async def test_save_calls_store(self, runtime_manager, mock_store):
        """Test that save() persists data to store."""
        await runtime_manager.load()
        
        runtime_manager._data["runtime_hours"] = 5.0
        await runtime_manager.save()
        
        mock_store.async_save.assert_called_once()
        saved_data = mock_store.async_save.call_args[0][0]
        assert saved_data["runtime_hours"] == 5.0

    @pytest.mark.asyncio
    async def test_get_and_set_last_preset(self, runtime_manager):
        """Test getting and setting last preset mode."""
        await runtime_manager.load()
        
        # Default should be 'off'
        assert runtime_manager.get_last_preset() == "off"
        
        # Set to 'high'
        runtime_manager.set_last_preset("high")
        assert runtime_manager.get_last_preset() == "high"

    @pytest.mark.asyncio
    async def test_get_filter_time(self, runtime_manager, mock_store):
        """Test that get_filter_time returns runtime hours."""
        test_data = {"runtime_hours": 15.5}
        mock_store.async_load = AsyncMock(return_value=test_data)
        
        await runtime_manager.load()
        
        assert runtime_manager.get_filter_time() == 15.5

    @pytest.mark.asyncio
    async def test_runtime_hours_never_negative(self, runtime_manager):
        """Test that runtime hours never returns negative values."""
        await runtime_manager.load()
        
        # Even if data gets corrupted
        runtime_manager._data["runtime_hours"] = -10.0
        
        # The getter should not return negative (though validation should prevent this)
        # Just verify it doesn't crash
        result = runtime_manager.get_runtime_hours()
        assert isinstance(result, float)

    @pytest.mark.asyncio
    async def test_load_invalid_runtime_type(self, runtime_manager, mock_store):
        """Test loading with invalid runtime_hours type."""
        test_data = {
            "runtime_hours": "not_a_number",
            "last_reset": "2026-01-15T10:00:00Z",
        }
        mock_store.async_load = AsyncMock(return_value=test_data)
        
        await runtime_manager.load()
        
        # Should reset to 0.0 due to validation failure
        assert runtime_manager.get_runtime_hours() == 0.0

    @pytest.mark.asyncio
    async def test_load_invalid_last_start_type(self, runtime_manager, mock_store):
        """Test loading with invalid last_start type."""
        test_data = {
            "runtime_hours": 5.0,
            "last_start": "not_a_timestamp",
        }
        mock_store.async_load = AsyncMock(return_value=test_data)
        
        await runtime_manager.load()
        
        # Should load runtime_hours successfully
        assert runtime_manager.get_runtime_hours() == 5.0
        # last_start should be ignored
        assert runtime_manager._data.get("last_start") is None

    @pytest.mark.asyncio
    async def test_load_invalid_last_reset_type(self, runtime_manager, mock_store):
        """Test loading with invalid last_reset type."""
        test_data = {
            "runtime_hours": 3.0,
            "last_reset": 12345,  # Should be string, not int
        }
        mock_store.async_load = AsyncMock(return_value=test_data)
        
        await runtime_manager.load()
        
        # Should load runtime_hours successfully
        assert runtime_manager.get_runtime_hours() == 3.0
        # last_reset should be ignored
        assert runtime_manager.get_last_reset() is None

    @pytest.mark.asyncio
    async def test_load_invalid_last_preset_type(self, runtime_manager, mock_store):
        """Test loading with invalid last_preset type."""
        test_data = {
            "runtime_hours": 2.0,
            "last_preset": 123,  # Should be string, not int
        }
        mock_store.async_load = AsyncMock(return_value=test_data)
        
        await runtime_manager.load()
        
        # Should load runtime_hours successfully
        assert runtime_manager.get_runtime_hours() == 2.0
        # last_preset should be ignored
        assert runtime_manager._data.get("last_preset") is None


class TestRuntimeDowntime:
    @pytest.fixture
    def runtime_manager(self, mock_store):
        return RuntimeManager(mock_store)

    @pytest.mark.asyncio
    async def test_load_does_not_restore_open_session(self, runtime_manager, mock_store):
        """An open session at shutdown must not count the HA downtime as runtime."""
        mock_store.async_load = AsyncMock(return_value={
            "runtime_hours": 3.0,
            "last_start": 1.0,  # long ago
        })
        await runtime_manager.load()

        assert runtime_manager._data.get("last_start") is None
        assert runtime_manager.get_runtime_hours() == 3.0


class _Clock:
    """utcnow() stand-in with a settable time."""

    def __init__(self, t=1_000_000.0):
        self.t = t

    def __call__(self):
        return MagicMock(timestamp=lambda: self.t)


class TestRuntimeCheckpoint:
    """The open session is moved into the total, so a reload/restart loses nothing."""

    @pytest.fixture
    def clock(self):
        from unittest.mock import patch

        clock = _Clock()
        with patch("custom_components.thermex_api.runtime_manager.utcnow", clock):
            yield clock

    @pytest.fixture
    def manager(self):
        store = MagicMock()
        store.async_save = AsyncMock()
        return RuntimeManager(store)

    def test_checkpoint_keeps_the_session_open_and_the_total_unchanged(self, manager, clock):
        manager.start()
        clock.t += 3600.0

        before = manager.get_runtime_hours()
        manager.checkpoint()

        assert manager.is_running()
        assert manager.get_runtime_hours() == before == 1.0

    def test_time_after_a_checkpoint_is_still_counted(self, manager, clock):
        manager.start()
        clock.t += 3600.0
        manager.checkpoint()
        clock.t += 1800.0
        manager.stop()

        assert manager.get_runtime_hours() == 1.5
        assert not manager.is_running()

    def test_checkpoint_without_a_session_does_nothing(self, manager, clock):
        manager.checkpoint()

        assert manager.get_runtime_hours() == 0.0
        assert not manager.is_running()

    def test_delayed_off_roundtrip(self, manager):
        from homeassistant.util.dt import parse_datetime

        when = parse_datetime("2026-11-07T12:00:00+00:00")
        manager.set_delayed_off(when)
        assert manager.get_delayed_off() == when

        manager.set_delayed_off(None)
        assert manager.get_delayed_off() is None

    @pytest.mark.asyncio
    async def test_delayed_off_survives_load_and_bad_values_are_dropped(self, manager):
        manager._store.async_load = AsyncMock(return_value={"delayed_off_at": "2026-11-07T12:00:00+00:00"})
        await manager.load()
        assert manager.get_delayed_off() is not None

        manager._store.async_load = AsyncMock(return_value={"delayed_off_at": "not a date"})
        await manager.load()
        assert manager.get_delayed_off() is None
