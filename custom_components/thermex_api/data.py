"""Runtime data for the Thermex integration."""
from dataclasses import dataclass

from homeassistant.config_entries import ConfigEntry

from .coordinator import ThermexCoordinator
from .hub import ThermexHub
from .runtime_manager import RuntimeManager


@dataclass
class ThermexData:
    """Objects shared by all platforms of one config entry."""

    hub: ThermexHub
    runtime_manager: RuntimeManager
    coordinator: ThermexCoordinator


type ThermexConfigEntry = ConfigEntry[ThermexData]
