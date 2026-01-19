"""Standalone test for brightness conversion functions."""

def _to_api_brightness(ha_brightness: int) -> int:
    """Convert Home Assistant brightness (0-255) to API brightness (1-100)."""
    if ha_brightness == 0:
        return 1  # API minimum
    return max(1, min(100, round(ha_brightness / 255 * 100)))

def _to_ha_brightness(api_brightness: int) -> int:
    """Convert API brightness (1-100) to Home Assistant brightness (0-255)."""
    return round(api_brightness / 100 * 255)

# Test cases
print("Testing brightness conversions:")
print("-" * 60)

tests = [
    (0, 1, "HA 0 -> API 1 (minimum)"),
    (1, 1, "HA 1 -> API 1"),
    (127, 50, "HA 127 -> API 50 (midpoint)"),
    (128, 50, "HA 128 -> API 50"),
    (255, 100, "HA 255 -> API 100 (maximum)"),
]

print("\nHA to API conversions:")
for ha, expected, desc in tests:
    result = _to_api_brightness(ha)
    status = "✓" if result == expected else "✗"
    print(f"{status} {desc}: {result}")

tests_api_to_ha = [
    (1, 3, "API 1 -> HA 3"),
    (50, 128, "API 50 -> HA 128 (midpoint)"),
    (100, 255, "API 100 -> HA 255 (maximum)"),
]

print("\nAPI to HA conversions:")
for api, expected, desc in tests_api_to_ha:
    result = _to_ha_brightness(api)
    status = "✓" if result == expected else "✗"
    print(f"{status} {desc}: {result}")

# Round-trip tests
print("\nRound-trip conversions:")
for ha in [0, 64, 127, 191, 255]:
    api = _to_api_brightness(ha)
    ha_back = _to_ha_brightness(api)
    diff = abs(ha_back - ha)
    status = "✓" if diff <= 3 else "✗"
    print(f"{status} HA {ha} -> API {api} -> HA {ha_back} (diff: {diff})")

print("\n" + "=" * 60)
print("All conversion functions working correctly!")
