"""Tests for the light entities."""
from unittest.mock import MagicMock

import pytest
from homeassistant.components.light import ColorMode

from custom_components.thermex_api.light import ThermexDecoLight, ThermexLight
from custom_components.thermex_api.state import DecolightState, LightState, ThermexState


@pytest.fixture
def light(coordinator, mock_hass):
    entity = ThermexLight(coordinator)
    entity.hass = mock_hass
    entity.async_write_ha_state = MagicMock()
    return entity


@pytest.fixture
def deco(coordinator, mock_hass):
    entity = ThermexDecoLight(coordinator)
    entity.hass = mock_hass
    entity.async_write_ha_state = MagicMock()
    return entity


class TestMainLight:
    def test_is_a_brightness_light(self, light):
        assert light.supported_color_modes == {ColorMode.BRIGHTNESS}
        assert light.color_mode == ColorMode.BRIGHTNESS
        assert light.unique_id == "test_thermex_hub_light"

    def test_unknown_state_is_off_with_default_brightness(self, light):
        assert light.is_on is False
        assert light.brightness == 204

    def test_state_comes_from_the_coordinator(self, light, coordinator):
        coordinator.data = ThermexState(light=LightState(on=True, brightness=50))

        assert light.is_on is True
        assert light.brightness == 128  # 50 % of 255

    def test_brightness_is_remembered_while_off(self, light, coordinator):
        coordinator.data = ThermexState(light=LightState(on=True, brightness=40))
        light._handle_coordinator_update()
        coordinator.data = ThermexState(light=LightState(on=False, brightness=0))
        light._handle_coordinator_update()

        assert light.is_on is False
        assert light.brightness == 102  # 40 % of 255

    def test_a_state_update_writes_state(self, light):
        light._handle_coordinator_update()

        light.async_write_ha_state.assert_called_once()

    @pytest.mark.asyncio
    async def test_turn_on_default(self, light, mock_hub):
        await light.async_turn_on()

        mock_hub.send_update.assert_awaited_once_with({"Light": {"lightonoff": 1, "lightbrightness": 80}})

    @pytest.mark.asyncio
    async def test_turn_on_with_brightness(self, light, mock_hub):
        await light.async_turn_on(brightness=128)

        assert mock_hub.send_update.call_args.args[0]["Light"]["lightbrightness"] == 50

    @pytest.mark.asyncio
    async def test_turn_on_returns_to_the_last_brightness(self, light, coordinator, mock_hub):
        coordinator.data = ThermexState(light=LightState(on=True, brightness=30))
        light._handle_coordinator_update()
        coordinator.data = ThermexState(light=LightState(on=False, brightness=0))
        light._handle_coordinator_update()

        await light.async_turn_on()

        assert mock_hub.send_update.call_args.args[0]["Light"]["lightbrightness"] == 30

    @pytest.mark.asyncio
    async def test_turn_off(self, light, mock_hub):
        await light.async_turn_off()

        mock_hub.send_update.assert_awaited_once_with({"Light": {"lightonoff": 0, "lightbrightness": 1}})

    @pytest.mark.asyncio
    async def test_state_is_not_assumed_after_a_command(self, light, mock_hub):
        """The hood may clamp or rewrite the value, so the state comes from the read-back."""
        await light.async_turn_on(brightness=255)

        assert light.is_on is False
        light.async_write_ha_state.assert_not_called()


class TestDecolight:
    def test_is_an_hs_light(self, deco):
        assert deco.supported_color_modes == {ColorMode.HS}
        assert deco.color_mode == ColorMode.HS
        assert deco.unique_id == "test_thermex_hub_decolight"

    def test_colour_comes_from_the_hoods_rgb(self, deco, coordinator):
        coordinator.data = ThermexState(decolight=DecolightState(on=True, brightness=100, rgb=(255, 0, 0)))
        deco._handle_coordinator_update()

        assert deco.hs_color == (0.0, 100.0)

    def test_colour_survives_being_switched_off(self, deco, coordinator):
        coordinator.data = ThermexState(decolight=DecolightState(on=True, brightness=100, rgb=(0, 255, 0)))
        deco._handle_coordinator_update()
        coordinator.data = ThermexState(decolight=DecolightState(on=False, brightness=0, rgb=(0, 0, 0)))
        deco._handle_coordinator_update()

        assert deco.is_on is False
        assert deco.hs_color == (120.0, 100.0)

    def test_colour_is_known_from_the_start(self, coordinator, mock_hass):
        coordinator.data = ThermexState(decolight=DecolightState(on=True, brightness=100, rgb=(0, 0, 255)))

        assert ThermexDecoLight(coordinator).hs_color == (240.0, 100.0)

    @pytest.mark.asyncio
    async def test_turn_on_after_off_reuses_the_last_colour(self, deco, coordinator, mock_hub):
        coordinator.data = ThermexState(decolight=DecolightState(on=True, brightness=100, rgb=(0, 0, 255)))
        deco._handle_coordinator_update()
        coordinator.data = ThermexState(decolight=DecolightState(on=False, brightness=0, rgb=(0, 0, 0)))
        deco._handle_coordinator_update()

        await deco.async_turn_on()

        payload = mock_hub.send_update.call_args.args[0]["Decolight"]
        assert (payload["decolightr"], payload["decolightg"], payload["decolightb"]) == (0, 0, 255)

    @pytest.mark.asyncio
    async def test_turn_on_with_rgb(self, deco, mock_hub):
        await deco.async_turn_on(rgb_color=(10, 20, 30), brightness=128)

        assert mock_hub.send_update.call_args.args[0] == {"Decolight": {
            "decolightonoff": 1, "decolightbrightness": 50,
            "decolightr": 10, "decolightg": 20, "decolightb": 30,
        }}

    @pytest.mark.asyncio
    async def test_turn_on_with_hs(self, deco, mock_hub):
        await deco.async_turn_on(hs_color=(0.0, 100.0))

        payload = mock_hub.send_update.call_args.args[0]["Decolight"]
        assert (payload["decolightr"], payload["decolightg"], payload["decolightb"]) == (255, 0, 0)

    @pytest.mark.asyncio
    async def test_turn_off(self, deco, mock_hub):
        await deco.async_turn_off()

        mock_hub.send_update.assert_awaited_once_with(
            {"Decolight": {"decolightonoff": 0, "decolightbrightness": 1}}
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("decolight,expected", [(False, {ThermexLight}), (True, {ThermexLight, ThermexDecoLight})])
async def test_setup_adds_the_decolight_only_when_enabled(
    coordinator, mock_hass, mock_config_entry, decolight, expected
):
    from custom_components.thermex_api.light import async_setup_entry

    mock_config_entry.options = {**mock_config_entry.options, "enable_decolight": decolight}
    mock_config_entry.runtime_data = MagicMock(coordinator=coordinator)
    add = MagicMock()

    await async_setup_entry(mock_hass, mock_config_entry, add)

    assert {type(e) for e in add.call_args.args[0]} == expected
