"""Tests for brightness conversion functions in light.py."""
import pytest
from custom_components.thermex_api.light import _to_api_brightness, _to_ha_brightness


class TestBrightnessConversion:
    """Test brightness conversion between Home Assistant (0-255) and API (1-100) ranges."""

    def test_to_api_brightness_zero(self):
        """Test conversion of HA brightness 0 returns API minimum of 1."""
        assert _to_api_brightness(0) == 1

    def test_to_api_brightness_minimum(self):
        """Test conversion of HA brightness 1 returns API value 1."""
        assert _to_api_brightness(1) == 1

    def test_to_api_brightness_low_values(self):
        """Test conversion of low HA brightness values."""
        # Test a few low values
        assert _to_api_brightness(10) == 4  # 10/255*100 = 3.92 -> 4
        assert _to_api_brightness(25) == 10  # 25/255*100 = 9.8 -> 10
        assert _to_api_brightness(50) == 20  # 50/255*100 = 19.6 -> 20

    def test_to_api_brightness_midpoint(self):
        """Test conversion of mid-range HA brightness."""
        assert _to_api_brightness(127) == 50  # 127/255*100 = 49.8 -> 50
        assert _to_api_brightness(128) == 50  # 128/255*100 = 50.2 -> 50

    def test_to_api_brightness_high_values(self):
        """Test conversion of high HA brightness values."""
        assert _to_api_brightness(200) == 78  # 200/255*100 = 78.4 -> 78
        assert _to_api_brightness(230) == 90  # 230/255*100 = 90.2 -> 90

    def test_to_api_brightness_maximum(self):
        """Test conversion of HA brightness 255 returns API maximum of 100."""
        assert _to_api_brightness(255) == 100

    def test_to_api_brightness_above_maximum(self):
        """Test conversion clamps values above 255 to API maximum."""
        assert _to_api_brightness(300) == 100
        assert _to_api_brightness(500) == 100
        assert _to_api_brightness(1000) == 100

    def test_to_api_brightness_negative(self):
        """Test conversion handles negative values by returning minimum."""
        assert _to_api_brightness(-1) == 1
        assert _to_api_brightness(-100) == 1

    def test_to_ha_brightness_minimum(self):
        """Test conversion of API brightness 1 returns HA value."""
        assert _to_ha_brightness(1) == 3  # 1/100*255 = 2.55 -> 3

    def test_to_ha_brightness_low_values(self):
        """Test conversion of low API brightness values."""
        assert _to_ha_brightness(5) == 13  # 5/100*255 = 12.75 -> 13
        assert _to_ha_brightness(10) == 26  # 10/100*255 = 25.5 -> 26
        assert _to_ha_brightness(20) == 51  # 20/100*255 = 51.0 -> 51

    def test_to_ha_brightness_midpoint(self):
        """Test conversion of mid-range API brightness."""
        assert _to_ha_brightness(50) == 128  # 50/100*255 = 127.5 -> 128

    def test_to_ha_brightness_high_values(self):
        """Test conversion of high API brightness values."""
        assert _to_ha_brightness(75) == 191  # 75/100*255 = 191.25 -> 191
        assert _to_ha_brightness(90) == 230  # 90/100*255 = 229.5 -> 230

    def test_to_ha_brightness_maximum(self):
        """Test conversion of API brightness 100 returns HA maximum of 255."""
        assert _to_ha_brightness(100) == 255

    def test_to_ha_brightness_above_maximum(self):
        """Test conversion doesn't clamp high values (API should enforce limits)."""
        # Note: We don't clamp in _to_ha_brightness since API should never send >100
        # But mathematically the conversion still works
        assert _to_ha_brightness(110) == 281  # 110/100*255 = 280.5 -> 281

    def test_to_ha_brightness_zero(self):
        """Test conversion of API brightness 0 (technically invalid but handle gracefully)."""
        # API minimum is 1, but if we receive 0, return 0
        assert _to_ha_brightness(0) == 0

    def test_roundtrip_conversion_boundaries(self):
        """Test round-trip conversion at boundary values."""
        # 0 -> 1 -> 3 (not perfect but acceptable)
        assert _to_ha_brightness(_to_api_brightness(0)) == 3
        
        # 255 -> 100 -> 255 (perfect)
        assert _to_ha_brightness(_to_api_brightness(255)) == 255

    def test_roundtrip_conversion_common_values(self):
        """Test round-trip conversion for common brightness values."""
        # Test some common values used in Home Assistant
        common_values = [51, 102, 128, 153, 204, 255]  # 20%, 40%, 50%, 60%, 80%, 100%
        
        for ha_value in common_values:
            api_value = _to_api_brightness(ha_value)
            converted_back = _to_ha_brightness(api_value)
            
            # Allow for rounding differences (within 2 units)
            assert abs(converted_back - ha_value) <= 2, \
                f"Round-trip failed: {ha_value} -> {api_value} -> {converted_back}"

    def test_api_percentage_mapping(self):
        """Test that API values map to expected percentage ranges."""
        # API 1% should be ~1% of 255
        assert 0 <= _to_ha_brightness(1) <= 10
        
        # API 25% should be ~25% of 255 (64)
        assert 60 <= _to_ha_brightness(25) <= 68
        
        # API 50% should be ~50% of 255 (127-128)
        assert 125 <= _to_ha_brightness(50) <= 130
        
        # API 75% should be ~75% of 255 (191)
        assert 188 <= _to_ha_brightness(75) <= 194
        
        # API 100% should be exactly 255
        assert _to_ha_brightness(100) == 255

    def test_ha_percentage_mapping(self):
        """Test that HA values map to expected API percentages."""
        # HA 0 should always map to API 1 (special case)
        assert _to_api_brightness(0) == 1
        
        # HA ~25% (64) should be ~25% API
        assert 24 <= _to_api_brightness(64) <= 26
        
        # HA 50% (127-128) should be ~50% API
        assert 49 <= _to_api_brightness(127) <= 51
        assert 49 <= _to_api_brightness(128) <= 51
        
        # HA 75% (191) should be ~75% API
        assert 74 <= _to_api_brightness(191) <= 76
        
        # HA 100% (255) should be exactly 100% API
        assert _to_api_brightness(255) == 100

    def test_conversion_precision(self):
        """Test that conversion maintains reasonable precision across the range."""
        # Test all HA values from 0-255
        for ha_brightness in range(0, 256):
            api_brightness = _to_api_brightness(ha_brightness)
            
            # Verify API value is in valid range
            assert 1 <= api_brightness <= 100, \
                f"HA {ha_brightness} -> API {api_brightness} out of range"
            
            # Convert back and verify we're within reasonable tolerance
            ha_back = _to_ha_brightness(api_brightness)
            diff = abs(ha_back - ha_brightness)
            
            # Allow tolerance of up to 2 units due to rounding (except for 0 which maps to 1->3)
            if ha_brightness == 0:
                assert diff <= 3, \
                    f"Round-trip precision failed for {ha_brightness}: {ha_brightness} -> {api_brightness} -> {ha_back}"
            else:
                assert diff <= 2, \
                    f"Round-trip precision failed for {ha_brightness}: {ha_brightness} -> {api_brightness} -> {ha_back}"

    def test_all_api_values_convert_back(self):
        """Test that all API values 1-100 convert to valid HA values."""
        for api_brightness in range(1, 101):
            ha_brightness = _to_ha_brightness(api_brightness)
            
            # Verify HA value is in valid range
            assert 0 <= ha_brightness <= 255, \
                f"API {api_brightness} -> HA {ha_brightness} out of range"

    def test_consistency_monotonic_increasing(self):
        """Test that conversions are monotonically increasing."""
        # HA to API should increase monotonically
        prev_api = 0
        for ha in range(0, 256):
            api = _to_api_brightness(ha)
            assert api >= prev_api, \
                f"HA to API not monotonic: HA {ha-1}->{prev_api}, HA {ha}->{api}"
            prev_api = api
        
        # API to HA should increase monotonically
        prev_ha = 0
        for api in range(1, 101):
            ha = _to_ha_brightness(api)
            assert ha >= prev_ha, \
                f"API to HA not monotonic: API {api-1}->{prev_ha}, API {api}->{ha}"
            prev_ha = ha

    def test_common_ui_percentages(self):
        """Test common UI percentage values convert correctly."""
        # Many UIs use 10% increments
        ui_percentages = [0, 10, 20, 30, 40, 50, 60, 70, 80, 90, 100]
        
        for percent in ui_percentages:
            ha_value = round(percent / 100 * 255)
            api_value = _to_api_brightness(ha_value)
            
            # Expected API value (with special case for 0)
            expected_api = 1 if percent == 0 else percent
            
            # Allow 1% tolerance
            assert abs(api_value - expected_api) <= 1, \
                f"UI {percent}% (HA {ha_value}) -> API {api_value}, expected ~{expected_api}"
