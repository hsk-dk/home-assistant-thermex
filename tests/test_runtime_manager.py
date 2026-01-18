"""Tests for RuntimeManager."""
import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock
from homeassistant.util.dt import utcnow

from custom_components.thermex_api.runtime_manager import RuntimeManager


class TestRuntimeManager:
    """Test RuntimeManager functionality."""

    @pytest.fixture
    def runtime_manager(self, mock_store, mock_hub):
        """Create a RuntimeManager instance."""
        return RuntimeManager(mock_store, mock_hub)

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
            "total_runtime_seconds": 7200,  # 2 hours
            "last_reset": "2026-01-15T10:00:00Z",
            "active_session_start": None,
        }
        mock_store.async_load = AsyncMock(return_value=test_data)
        
        await runtime_manager.load()
        
        assert runtime_manager.get_runtime_hours() == 2.0
        assert runtime_manager.get_last_reset() == "2026-01-15T10:00:00Z"

    @pytest.mark.asyncio
    async def test_load_validates_negative_runtime(self, runtime_manager, mock_store):
        """Test that negative runtime values are rejected."""
        test_data = {
            "total_runtime_seconds": -100,
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
            "total_runtime_seconds": 3600,
            "last_reset": "not-a-valid-timestamp",
        }
        mock_store.async_load = AsyncMock(return_value=test_data)
        
        await runtime_manager.load()
        
        # Should load runtime but clear invalid timestamp
        assert runtime_manager.get_runtime_hours() == 1.0
        assert runtime_manager.get_last_reset() is None

    @pytest.mark.asyncio
    async def test_start_session(self, runtime_manager):
        """Test starting a runtime tracking session."""
        await runtime_manager.load()
        
        runtime_manager.start_session()
        
        assert runtime_manager._active_session_start is not None
        assert isinstance(runtime_manager._active_session_start, datetime)

    @pytest.mark.asyncio
    async def test_stop_session_accumulates_time(self, runtime_manager):
        """Test stopping a session accumulates runtime."""
        await runtime_manager.load()
        
        # Start session
        runtime_manager.start_session()
        
        # Manually set start time to 1 hour ago
        runtime_manager._active_session_start = utcnow() - timedelta(hours=1)
        
        # Stop session
        await runtime_manager.stop_session()
        
        # Should have accumulated ~1 hour (allowing small tolerance)
        assert 0.95 <= runtime_manager.get_runtime_hours() <= 1.05
        assert runtime_manager._active_session_start is None

    @pytest.mark.asyncio
    async def test_stop_session_without_start(self, runtime_manager):
        """Test stopping without starting does nothing."""
        await runtime_manager.load()
        
        initial_runtime = runtime_manager.get_runtime_hours()
        await runtime_manager.stop_session()
        
        assert runtime_manager.get_runtime_hours() == initial_runtime

    @pytest.mark.asyncio
    async def test_get_runtime_hours_with_active_session(self, runtime_manager):
        """Test runtime calculation includes active session."""
        await runtime_manager.load()
        
        # Set initial runtime to 2 hours
        runtime_manager._total_runtime_seconds = 7200
        
        # Start session 30 minutes ago
        runtime_manager._active_session_start = utcnow() - timedelta(minutes=30)
        
        runtime = runtime_manager.get_runtime_hours()
        
        # Should be ~2.5 hours (2 stored + 0.5 active)
        assert 2.4 <= runtime <= 2.6

    @pytest.mark.asyncio
    async def test_reset_runtime(self, runtime_manager):
        """Test resetting runtime clears all data."""
        await runtime_manager.load()
        
        # Set some runtime data
        runtime_manager._total_runtime_seconds = 10000
        runtime_manager.start_session()
        
        # Reset
        await runtime_manager.reset_runtime()
        
        assert runtime_manager.get_runtime_hours() == 0.0
        assert runtime_manager._active_session_start is None
        assert runtime_manager.get_last_reset() is not None

    @pytest.mark.asyncio
    async def test_get_days_since_reset(self, runtime_manager, mock_store):
        """Test calculating days since last reset."""
        # Set reset time to 5 days ago
        five_days_ago = utcnow() - timedelta(days=5)
        test_data = {
            "total_runtime_seconds": 1000,
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
        
        runtime_manager._total_runtime_seconds = 5000
        await runtime_manager._save()
        
        mock_store.async_save.assert_called_once()
        saved_data = mock_store.async_save.call_args[0][0]
        assert saved_data["total_runtime_seconds"] == 5000

    @pytest.mark.asyncio
    async def test_multiple_start_sessions_ignored(self, runtime_manager):
        """Test that starting an already active session is ignored."""
        await runtime_manager.load()
        
        runtime_manager.start_session()
        first_start = runtime_manager._active_session_start
        
        # Try starting again
        runtime_manager.start_session()
        second_start = runtime_manager._active_session_start
        
        # Should be the same start time
        assert first_start == second_start

    @pytest.mark.asyncio
    async def test_runtime_hours_never_negative(self, runtime_manager):
        """Test that runtime hours never returns negative values."""
        await runtime_manager.load()
        
        # Even if data gets corrupted
        runtime_manager._total_runtime_seconds = -1000
        
        assert runtime_manager.get_runtime_hours() >= 0.0
