"""Typed state of the hood, parsed from the hood's Status and Notify messages."""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
from typing import Any

# The four levels of the hood (the remote shows the same four). "off" is not a preset.
PRESET_MODES = ["low", "medium", "high", "boost"]
SPEED_BY_PRESET = {"off": 0, "low": 1, "medium": 2, "high": 3, "boost": 4}
PRESET_BY_SPEED = {speed: mode for mode, speed in SPEED_BY_PRESET.items()}


@dataclass(frozen=True, slots=True)
class FanState:
    """The fan as the hood reports it."""

    on: bool
    speed: int  # 0 (off) .. 4 (boost)

    @property
    def running(self) -> bool:
        """The hood keeps a stale speed while off, so both must say "on"."""
        return self.on and self.speed != 0


@dataclass(frozen=True, slots=True)
class LightState:
    """The main light as the hood reports it."""

    on: bool
    brightness: int  # 1-100; the hood reports 0 while off


@dataclass(frozen=True, slots=True)
class DecolightState:
    """The Decolight as the hood reports it."""

    on: bool
    brightness: int  # 1-100; the hood reports 0 while off
    rgb: tuple[int, int, int]  # the hood reports 0, 0, 0 while off


@dataclass(frozen=True, slots=True)
class ThermexState:
    """Everything the hood has told us; a section is None until it was reported."""

    fan: FanState | None = None
    light: LightState | None = None
    decolight: DecolightState | None = None


def _parse_fan(section: Mapping[str, Any]) -> FanState:
    return FanState(
        on=bool(section.get("fanonoff", 0)),
        speed=int(section.get("fanspeed", 0) or 0),
    )


def _parse_light(section: Mapping[str, Any]) -> LightState:
    return LightState(
        on=bool(section.get("lightonoff", 0)),
        brightness=int(section.get("lightbrightness", 1) or 0),
    )


def _parse_decolight(section: Mapping[str, Any]) -> DecolightState:
    return DecolightState(
        on=bool(section.get("decolightonoff", 0)),
        brightness=int(section.get("decolightbrightness", 1) or 0),
        rgb=(
            int(section.get("decolightr", 0) or 0),
            int(section.get("decolightg", 0) or 0),
            int(section.get("decolightb", 0) or 0),
        ),
    )


def merge_status(state: ThermexState, data: Mapping[str, Any]) -> ThermexState:
    """Return `state` updated with the sections found in a Status or Notify `Data`.

    The hood's keys are case-insensitive, and a Notify may carry only some of the
    sections, so everything not mentioned is kept as it was. Unknown sections and
    malformed values are ignored.
    """
    updates: dict[str, Any] = {}
    for key, section in data.items():
        if not isinstance(section, Mapping) or not isinstance(key, str):
            continue
        name = key.lower()
        try:
            if name == "fan":
                updates["fan"] = _parse_fan(section)
            elif name == "light":
                updates["light"] = _parse_light(section)
            elif name == "decolight":
                updates["decolight"] = _parse_decolight(section)
        except (TypeError, ValueError):
            continue
    return replace(state, **updates) if updates else state
