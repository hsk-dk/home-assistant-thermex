"""Tests for light entities."""
import pytest
from unittest.mock import MagicMock
from homeassistant.components.light import ColorMode

from custom_components.thermex_api.light import ThermexLight, ThermexDecoLight


class TestThermexLight:
    """Test ThermexLight entity."""

    @pytest.fixture
    def light_entity(self, mock_hub, mock_hass):
        """Create a ThermexLight entity."""
        light = ThermexLight(mock_hub)
        light.hass = mock_hass
        return light

    def test_light_initialization(self, light_entity, mock_hub):
        """Test light entity initialization."""
        assert light_entity._hub == mock_hub
        assert light_entity.is_on is False
        assert light_entity._brightness == 204  # DEFAULT_BRIGHTNESS

    def test_light_color_mode(self, light_entity):
        """Test light supports brightness mode."""
        assert ColorMode.BRIGHTNESS in light_entity.supported_color_modes
        assert light_entity.color_mode == ColorMode.BRIGHTNESS

    @pytest.mark.asyncio
    async def test_light_turn_on_default(self, light_entity, mock_hub):
        """Test turning on light with default brightness."""
        await light_entity.async_turn_on()
        
        mock_hub.send_request.assert_called_once()
        call_args = mock_hub.send_request.call_args[0]
        assert call_args[0] == "Update"
        assert call_args[1]["Light"]["lightonoff"] == 1
        assert call_args[1]["Light"]["lightbrightness"] == 204

    @pytest.mark.asyncio
    async def test_light_turn_on_with_brightness(self, light_entity, mock_hub):
        """Test turning on light with specific brightness."""
        await light_entity.async_turn_on(brightness=128)
        
        call_args = mock_hub.send_request.call_args[0]
        assert call_args[1]["Light"]["lightbrightness"] == 128

    @pytest.mark.asyncio
    async def test_light_turn_off(self, light_entity, mock_hub):
        """Test turning off light."""
        light_entity._is_on = True
        
        await light_entity.async_turn_off()
        
        mock_hub.send_request.assert_called_once()
        call_args = mock_hub.send_request.call_args[0]
        assert call_args[1]["Light"]["lightonoff"] == 0

    def test_light_handle_notify_updates_state(self, light_entity):
        """Test light state updates from notifications."""
        light_entity._handle_notify("light", {
            "Light": {
                "lightonoff": 1,
                "lightbrightness": 150,
            }
        })
        
        assert light_entity.is_on is True
        assert light_entity._brightness == 150

    def test_light_brightness_clamping(self, light_entity):
        """Test brightness values are clamped to valid range."""
        # Test below min brightness (gets clamped to 1)
        result = light_entity._clamp_brightness(-10)
        assert result == 1  # MIN_BRIGHTNESS
        
        # Test at min brightness
        result = light_entity._clamp_brightness(1)
        assert result == 1
        
        # Test max brightness
        result = light_entity._clamp_brightness(300)
        assert result == 255  # MAX_BRIGHTNESS
        
        # Test normal value
        result = light_entity._clamp_brightness(128)
        assert result == 128

    def test_light_remembers_last_brightness(self, light_entity):
        """Test light remembers last brightness when turned on."""
        light_entity._handle_notify("light", {
            "Light": {
                "lightonoff": 1,
                "lightbrightness": 180,
            }
        })
        
        assert light_entity._last_brightness == 180

    def test_light_ignores_non_light_notifications(self, light_entity):
        """Test light ignores notifications for other entities."""
        original_state = light_entity.is_on
        
        light_entity._handle_notify("fan", {"Fan": {"fanspeed": 2}})
        
        assert light_entity.is_on == original_state


class TestThermexDecoLight:
    """Test ThermexDecoLight entity."""

    @pytest.fixture
    def decolight_entity(self, mock_hub, mock_hass):
        """Create a ThermexDecoLight entity."""
        light = ThermexDecoLight(mock_hub)
        light.hass = mock_hass
        return light

    def test_decolight_initialization(self, decolight_entity, mock_hub):
        """Test deco light entity initialization."""
        assert decolight_entity._hub == mock_hub
        assert decolight_entity.is_on is False
        assert decolight_entity._hs_color == (0.0, 0.0)

    def test_decolight_color_modes(self, decolight_entity):
        """Test deco light supports HS and brightness modes."""
        assert ColorMode.HS in decolight_entity.supported_color_modes
        assert ColorMode.BRIGHTNESS in decolight_entity.supported_color_modes
        assert decolight_entity.color_mode == ColorMode.HS

    @pytest.mark.asyncio
    async def test_decolight_turn_on_with_color(self, decolight_entity, mock_hub):
        """Test turning on deco light with RGB color."""
        await decolight_entity.async_turn_on(
            brightness=200,
            rgb_color=(255, 0, 0)  # Red
        )
        
        call_args = mock_hub.send_request.call_args[0]
        assert call_args[1]["Decolight"]["decolightonoff"] == 1
        assert call_args[1]["Decolight"]["decolightbrightness"] == 200
        assert call_args[1]["Decolight"]["decolightr"] == 255
        assert call_args[1]["Decolight"]["decolightg"] == 0
        assert call_args[1]["Decolight"]["decolightb"] == 0

    @pytest.mark.asyncio
    async def test_decolight_turn_off(self, decolight_entity, mock_hub):
        """Test turning off deco light."""
        decolight_entity._is_on = True
        
        await decolight_entity.async_turn_off()
        
        call_args = mock_hub.send_request.call_args[0]
        assert call_args[1]["Decolight"]["decolightonoff"] == 0

    def test_decolight_handle_notify_with_color(self, decolight_entity):
        """Test deco light updates from notifications including color."""
        decolight_entity._handle_notify("decolight", {
            "Decolight": {
                "decolightonoff": 1,
                "decolightbrightness": 150,
                "decolightr": 0,
                "decolightg": 255,
                "decolightb": 0,
            }
        })
        
        assert decolight_entity.is_on is True
        assert decolight_entity._brightness == 150
        # Color should be converted to HS (green)
        assert decolight_entity._hs_color[0] == 120.0  # Green hue

    def test_decolight_ignores_wrong_notifications(self, decolight_entity):
        """Test deco light ignores non-decolight notifications."""
        original_state = decolight_entity.is_on
        
        decolight_entity._handle_notify("light", {"Light": {"lightonoff": 1}})
        
        assert decolight_entity.is_on == original_state
