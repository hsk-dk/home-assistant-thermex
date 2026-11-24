"""RuntimeManager: damaged or odd data in the store never breaks the integration."""
import logging
from unittest.mock import AsyncMock

import pytest

from custom_components.thermex_api.runtime_manager import RuntimeManager

LOGGER = "custom_components.thermex_api.runtime_manager"


@pytest.fixture
def manager(mock_store):
    return RuntimeManager(mock_store)


@pytest.mark.parametrize("stored", [["not", "a", "dict"], "text", 42])
async def test_data_that_is_not_a_dict_starts_fresh(manager, mock_store, caplog, stored):
    mock_store.async_load = AsyncMock(return_value=stored)

    with caplog.at_level(logging.WARNING, logger=LOGGER):
        await manager.load()

    assert manager.get_runtime_hours() == 0.0
    assert manager.get_last_reset() is None
    assert manager.get_last_preset() == "off"
    assert any("Corrupted runtime data" in r.getMessage() for r in caplog.records)


async def test_a_preset_that_is_not_text_is_ignored(manager, mock_store, caplog):
    mock_store.async_load = AsyncMock(return_value={"runtime_hours": 3, "last_preset": 5})

    with caplog.at_level(logging.WARNING, logger=LOGGER):
        await manager.load()

    assert manager.get_last_preset() == "off"
    assert manager.get_runtime_hours() == 3.0  # the rest of the data is kept
    assert any("Invalid last_preset" in r.getMessage() for r in caplog.records)


async def test_a_failing_store_starts_fresh_instead_of_failing_setup(manager, mock_store, caplog):
    mock_store.async_load = AsyncMock(side_effect=OSError("disk gone"))

    with caplog.at_level(logging.ERROR, logger=LOGGER):
        await manager.load()

    assert manager.get_runtime_hours() == 0.0
    assert any("disk gone" in r.getMessage() for r in caplog.records)


@pytest.mark.parametrize(
    "last_reset",
    [
        "garbage",  # not a date at all
        "2026-13-45T10:00:00Z",  # looks like one, but impossible
        "2026-01-15T10:00:00",  # no time zone: cannot be compared with now
    ],
)
async def test_an_unreadable_reset_date_gives_no_age(manager, mock_store, caplog, last_reset):
    mock_store.async_load = AsyncMock(return_value={"last_reset": last_reset})
    await manager.load()

    with caplog.at_level(logging.WARNING, logger=LOGGER):
        assert manager.get_days_since_reset() is None

    assert any("days since reset" in r.getMessage() for r in caplog.records)
    assert manager.get_last_reset() == last_reset  # still reported as stored


async def test_a_stored_preset_is_restored(manager, mock_store):
    mock_store.async_load = AsyncMock(return_value={"last_preset": "boost"})

    await manager.load()

    assert manager.get_last_preset() == "boost"
