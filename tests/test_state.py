"""Parsing of the hood's Status/Notify data into typed state."""
from custom_components.thermex_api.state import (
    DecolightState,
    FanState,
    LightState,
    ThermexState,
    merge_status,
)


def test_full_status_is_parsed():
    state = merge_status(ThermexState(), {
        "Fan": {"fanonoff": 1, "fanspeed": 3},
        "Light": {"lightonoff": 1, "lightbrightness": 80},
        "Decolight": {
            "decolightonoff": 1, "decolightbrightness": 40,
            "decolightr": 255, "decolightg": 10, "decolightb": 0,
        },
    })

    assert state.fan == FanState(on=True, speed=3)
    assert state.light == LightState(on=True, brightness=80)
    assert state.decolight == DecolightState(on=True, brightness=40, rgb=(255, 10, 0))


def test_keys_are_case_insensitive():
    state = merge_status(ThermexState(), {"fan": {"fanonoff": 1, "fanspeed": 1}})

    assert state.fan == FanState(on=True, speed=1)


def test_a_partial_update_keeps_the_other_sections():
    before = merge_status(ThermexState(), {
        "Fan": {"fanonoff": 1, "fanspeed": 2},
        "Light": {"lightonoff": 1, "lightbrightness": 50},
    })

    after = merge_status(before, {"Light": {"lightonoff": 0, "lightbrightness": 0}})

    assert after.fan == before.fan
    assert after.light == LightState(on=False, brightness=0)


def test_unknown_sections_and_malformed_values_are_ignored():
    before = ThermexState(fan=FanState(on=True, speed=2))

    state = merge_status(before, {
        "Alert": {"x": 1},
        "Fan": "not a section",
        "Light": {"lightonoff": 1, "lightbrightness": "high"},
        7: {"fanonoff": 1},
    })

    assert state == before


def test_missing_fields_default_to_off():
    state = merge_status(ThermexState(), {"Fan": {}, "Light": {}})

    assert state.fan == FanState(on=False, speed=0)
    assert state.light == LightState(on=False, brightness=1)


def test_fan_runs_only_when_switch_and_speed_agree():
    """The hood keeps a stale speed while off."""
    assert FanState(on=True, speed=2).running is True
    assert FanState(on=False, speed=2).running is False
    assert FanState(on=True, speed=0).running is False
