"""Actions (services): registered once, documented, translated."""
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml

from custom_components.thermex_api import FAN_ACTIONS, async_setup

COMPONENT = Path(__file__).parent.parent / "custom_components" / "thermex_api"


@pytest.mark.asyncio
async def test_actions_are_registered_once_in_async_setup(mock_hass):
    with patch("custom_components.thermex_api.service.async_register_platform_entity_service") as register:
        assert await async_setup(mock_hass, {}) is True

    names = {c.args[2] for c in register.call_args_list}
    assert names == {"reset_runtime", "start_delayed_off", "cancel_delayed_off"}
    for call in register.call_args_list:
        assert call.args[1] == "thermex_api"
        assert call.kwargs["entity_domain"] == "fan"
        assert call.kwargs["func"] == FAN_ACTIONS[call.args[2]]


def test_every_registered_action_targets_fan_entities_of_this_integration():
    services = yaml.safe_load((COMPONENT / "services.yaml").read_text(encoding="utf-8"))

    assert set(services) == set(FAN_ACTIONS)
    for name, definition in services.items():
        assert definition["target"]["entity"] == {"integration": "thermex_api", "domain": "fan"}, name


@pytest.mark.parametrize("path", sorted((COMPONENT / "translations").glob("*.json")), ids=lambda p: p.name)
def test_actions_and_errors_are_translated(path):
    data = json.loads(path.read_text(encoding="utf-8-sig"))

    assert set(data["services"]) == set(FAN_ACTIONS)
    for name, text in data["services"].items():
        assert text["name"] and text["description"], name
    for key in ("fan_not_running", "fan_entity_not_found", "cannot_connect", "invalid_auth", "request_rejected"):
        assert data["exceptions"][key]["message"], key


def test_fan_methods_exist_for_every_action():
    from custom_components.thermex_api.fan import ThermexFan

    for method in FAN_ACTIONS.values():
        assert callable(getattr(ThermexFan, method)), method
