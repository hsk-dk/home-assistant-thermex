"""Tests for RuntimeManager."""
import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, mock_open, patch

from custom_components.thermex_api.runtime_manager import RuntimeManager


class TestRuntimeManager:
    """Test RuntimeManager functionality."""

    @pytest.fixture
    def runtime_manager(self, mock_hass, mock_store):
        """Create a RuntimeManager instance."""
        return RuntimeManager(mock_hass, "test_entity", mock_store)

    @pytest.mark.asyncio
    async def test_load_no_data(self, runtime_manager, mock_store):
        """Test load when no data exists."""
        mock_store.async_load.return_value = None
        
        await runtime_manager.load()
        
        assert runtime_manager.get_total_seconds() == 0
        assert runtime_manager.get_last_reset() is None

    @pytest.mark.asyncio
    async def test_load_with_data(self, runtime_manager, mock_store):
        """Test load with existing data."""
        now = datetime.now(timezone.utc)
        mock_store.async_load.return_value = {
            "total_seconds": 3600,
            "last_reset": now.isoformat(),
            "start_time": None,
        }
        
        await runtime_manager.load()
        
        assert runtime_manager.get_total_seconds() == 3600
        assert runtime_manager.get_last_reset() == now

    @pytest.mark.asyncio
    async def test_save(self, runtime_manager, mock_store):
        """Test save stores data correctly."""
        runtime_manager._total_seconds = 7200
        runtime_manager._last_reset = datetime.now(timezone.utc)
        
        await runtime_manager.save()
        
        mock_store.async_save.assert_called_once()
        saved_data = mock_store.async_save.call_args[0][0]
        assert saved_data["total_seconds"] == 7200
        assert "last_reset" in saved_data

    def test_start_tracking(self, runtime_manager):
        """Test starting tracking."""
        runtime_manager.start_tracking()
        
        assert runtime_manager.is_running()
        assert runtime_manager._start_time is not None

    def test_stop_tracking_accumulates_time(self, runtime_manager):
        """Test stopping tracking accumulates elapsed time."""
        runtime_manager._start_time = datetime.now(timezone.utc) - timedelta(seconds=60)
        
        runtime_manager.stop_tracking()
        
        assert not runtime_manager.is_running()
        assert runtime_manager.get_total_seconds() >= 60

    def test_stop_tracking_when_not_running(self, runtime_manager):
        """Test stopping when not running does nothing."""
        initial_total = runtime_manager.get_total_seconds()
        
        runtime_manager.stop_tracking()
        
        assert runtime_manager.get_total_seconds() == initial_total

    def test_reset_clears_data(self, runtime_manager):
        """Test reset clears all tracking data."""
        runtime_manager._total_seconds = 3600
        runtime_manager._start_time = datetime.now(timezone.utc)
        
        runtime_manager.reset()
        
        assert runtime_manager.get_total_seconds() == 0
        assert not runtime_manager.is_running()
        assert runtime_manager.get_last_reset() is not None

    def test_get_total_seconds_while_running(self, runtime_manager):
        """Test get_total_seconds includes current runtime."""
        runtime_manager._total_seconds = 100
        runtime_manager._start_time = datetime.now(timezone.utc) - timedelta(seconds=50)
        
        total = runtime_manager.get_total_seconds()
        
        assert total >= 150  # 100 + 50

    def test_get_total_seconds_when_stopped(self, runtime_manager):
        """Test get_total_seconds when stopped."""
        runtime_manager._total_seconds = 300
        
        assert runtime_manager.get_total_seconds() == 300

    def test_format_runtime(self, runtime_manager):
        """Test runtime formatting."""
        runtime_manager._total_seconds = 3665  # 1h 1m 5s
        
        formatted = runtime_manager.format_runtime()
        
        assert "1h" in formatted
        assert "1m" in formatted
