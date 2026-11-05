"""Cross-cutting checks for how the entities are modelled."""
import json
from pathlib import Path

import pytest

from custom_components.thermex_api import binary_sensor, button, fan, light, sensor

COMPONENT = Path(__file__).parent.parent / "custom_components" / "thermex_api"


@pytest.mark.parametrize("module,expected", [
    (light, 1), (fan, 1), (button, 1),   # commands one at a time
    (sensor, 0), (binary_sensor, 0),     # read-only
])
def test_parallel_updates_is_set_explicitly(module, expected):
    assert module.PARALLEL_UPDATES == expected


def test_icons_json_matches_translated_entities():
    """Every icon key must refer to an entity translation key that exists."""
    icons = json.loads((COMPONENT / "icons.json").read_text(encoding="utf-8"))
    en = json.loads((COMPONENT / "translations" / "en.json").read_text(encoding="utf-8-sig"))

    for domain, entities in icons["entity"].items():
        for key in entities:
            assert key in en["entity"][domain], f"{domain}.{key} has an icon but no translation"
    assert set(icons["services"]) == set(en["services"])


def test_connection_states_are_translated_in_every_language():
    from custom_components.thermex_api.sensor import CONNECTION_STATES

    for path in (COMPONENT / "translations").glob("*.json"):
        data = json.loads(path.read_text(encoding="utf-8-sig"))
        states = data["entity"]["sensor"]["thermex_sensor_connection_status"]["state"]
        assert set(states) == set(CONNECTION_STATES), path.name
