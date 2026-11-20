"""Tests for the buttons."""
from unittest.mock import MagicMock

import pytest
from homeassistant.const import EntityCategory
from homeassistant.exceptions import ServiceValidationError

from custom_components.thermex_api.button import (
    DelayedTurnOffButton,
    ResetRuntimeButton,
    async_setup_entry,
)


@pytest.mark.asyncio
async def test_setup(coordinator, mock_hass, mock_config_entry):
    mock_config_entry.runtime_data = MagicMock(coordinator=coordinator)
    add = MagicMock()

    await async_setup_entry(mock_hass, mock_config_entry, add)

    assert {type(e) for e in add.call_args.args[0]} == {ResetRuntimeButton, DelayedTurnOffButton}


class TestResetRuntimeButton:
    def test_modelling(self, coordinator, mock_hub):
        mock_hub.available = False
        button = ResetRuntimeButton(coordinator)

        assert button.unique_id == "test_thermex_hub_reset_runtime"
        assert button.entity_category == EntityCategory.CONFIG
        assert button.available is True  # only resets stored data

    @pytest.mark.asyncio
    async def test_press_resets_the_counter(self, coordinator):
        await ResetRuntimeButton(coordinator).async_press()

        coordinator.async_reset_runtime.assert_awaited_once()


class TestDelayedTurnOffButton:
    def test_modelling(self, coordinator, mock_hub):
        button = DelayedTurnOffButton(coordinator)

        assert button.unique_id == "test_thermex_hub_delayed_turn_off"
        assert button.device_info == mock_hub.device_info
        assert button.available is True

        mock_hub.available = False
        assert button.available is False

    @pytest.mark.asyncio
    async def test_press_starts_the_timer(self, coordinator, delayed_off):
        await DelayedTurnOffButton(coordinator).async_press()

        delayed_off.async_start.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_errors_reach_the_user(self, coordinator, delayed_off):
        delayed_off.async_start.side_effect = ServiceValidationError(
            translation_domain="thermex_api", translation_key="fan_not_running"
        )

        with pytest.raises(ServiceValidationError):
            await DelayedTurnOffButton(coordinator).async_press()
