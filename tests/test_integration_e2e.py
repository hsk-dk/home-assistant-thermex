"""End-to-end: the real integration in a real Home Assistant, talking to a fake hood."""
import asyncio
import json
from unittest.mock import patch

import pytest
from aiohttp import WSMsgType, web
from aiohttp.test_utils import TestServer
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import STATE_OFF, STATE_ON, STATE_UNAVAILABLE
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.thermex_api.const import DOMAIN

DEVICE_ID = "thermex_e2e"
PASSWORD = "secret"


class FakeHood:
    """Speaks enough of the ESP-API: it answers like the real hood does."""

    def __init__(self) -> None:
        self.state = {
            "Fan": {"fanonoff": 0, "fanspeed": 0},
            "Light": {"lightonoff": 0, "lightbrightness": 0},
            "Decolight": {
                "decolightonoff": 0, "decolightbrightness": 0,
                "decolightr": 0, "decolightg": 0, "decolightb": 0,
            },
        }
        self.updates: list[dict] = []
        self.sockets: list[web.WebSocketResponse] = []

    async def handler(self, request: web.Request) -> web.WebSocketResponse:
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        self.sockets.append(ws)
        authenticated = False
        async for msg in ws:
            if msg.type != WSMsgType.TEXT:
                continue
            payload = json.loads(msg.data)
            req = payload["Request"].lower()
            if req == "authenticate":
                authenticated = payload["Data"]["Code"] == PASSWORD
                await ws.send_json({"Response": "Authenticate", "Status": 200 if authenticated else 401})
            elif req == "protocolversion":
                await ws.send_json({"Response": "ProtocolVersion", "Status": 200,
                                    "Data": {"MajorVersion": 1, "MinorVersion": 1}})
            elif not authenticated:
                await ws.send_json({"Response": payload["Request"], "Status": 401})
            elif req == "status":
                await ws.send_json({"Response": "Status", "Status": 200, "Data": self.state})
            elif req == "update":
                self.updates.append(payload["Data"])
                for section, values in payload["Data"].items():
                    self.state[section].update(values)
                    if section == "Light" and not values.get("lightonoff"):
                        self.state[section]["lightbrightness"] = 0
                await ws.send_json({"Response": "Update", "Status": 200})
        return ws

    async def notify(self, section: str, values: dict) -> None:
        """The hood tells everyone about a change made on its remote."""
        self.state[section].update(values)
        for ws in self.sockets:
            if not ws.closed:
                await ws.send_json({"Notify": section, "Data": {section: self.state[section]}})


@pytest.fixture
async def hood(socket_enabled):
    fake = FakeHood()
    app = web.Application()
    app.router.add_get("/api", fake.handler)
    server = TestServer(app)
    await server.start_server()
    fake.port = server.port
    with patch("custom_components.thermex_api.hub.DEFAULT_PORT", server.port):
        yield fake
    await server.close()


@pytest.fixture
async def entry(hass, hood, enable_custom_integrations):
    config_entry = MockConfigEntry(
        domain=DOMAIN,
        version=2,
        unique_id=DEVICE_ID,
        data={"host": "127.0.0.1", "api_key": PASSWORD, "device_id": DEVICE_ID},
        options={"enable_decolight": True, "fan_auto_off_delay": 5},
    )
    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    yield config_entry
    # close the connection before the fake hood shuts down
    if config_entry.state is ConfigEntryState.LOADED:
        await hass.config_entries.async_unload(config_entry.entry_id)
        await hass.async_block_till_done()


def entity_id(hass, domain: str, suffix: str) -> str:
    found = er.async_get(hass).async_get_entity_id(domain, DOMAIN, f"{DEVICE_ID}_{suffix}")
    assert found, f"{domain}.{suffix} was not created"
    return found


async def settle(hass, seconds: float = 0.2) -> None:
    await asyncio.sleep(seconds)
    await hass.async_block_till_done()


async def test_entities_start_with_the_hoods_state(hass, entry):
    assert entry.state is ConfigEntryState.LOADED
    assert hass.states.get(entity_id(hass, "fan", "fan")).state == STATE_OFF
    assert hass.states.get(entity_id(hass, "light", "light")).state == STATE_OFF
    assert hass.states.get(entity_id(hass, "light", "decolight")).state == STATE_OFF
    assert hass.states.get(entity_id(hass, "sensor", "runtime_hours")).state == "0.0"
    assert hass.states.get(entity_id(hass, "binary_sensor", "threshold_alert")).state == STATE_OFF


async def test_a_change_on_the_remote_reaches_home_assistant(hass, entry, hood):
    await hood.notify("Fan", {"fanonoff": 1, "fanspeed": 3})
    await settle(hass)

    fan = hass.states.get(entity_id(hass, "fan", "fan"))
    assert fan.state == STATE_ON
    assert fan.attributes["preset_mode"] == "high"
    assert fan.attributes["percentage"] == 75


async def test_fan_commands_go_to_the_hood_and_the_state_follows_the_readback(hass, entry, hood):
    fan_id = entity_id(hass, "fan", "fan")

    await hass.services.async_call("fan", "set_preset_mode", {"entity_id": fan_id, "preset_mode": "boost"}, blocking=True)
    await settle(hass)

    assert hood.updates[-1] == {"Fan": {"fanonoff": 1, "fanspeed": 4}}
    assert hass.states.get(fan_id).attributes["preset_mode"] == "boost"

    await hass.services.async_call("fan", "turn_off", {"entity_id": fan_id}, blocking=True)
    await settle(hass)

    assert hood.updates[-1] == {"Fan": {"fanonoff": 0, "fanspeed": 0}}
    assert hass.states.get(fan_id).state == STATE_OFF
    assert hass.states.get(fan_id).attributes["preset_mode"] is None


async def test_turn_on_returns_to_the_last_level(hass, entry, hood):
    fan_id = entity_id(hass, "fan", "fan")
    await hass.services.async_call("fan", "set_preset_mode", {"entity_id": fan_id, "preset_mode": "high"}, blocking=True)
    await settle(hass)
    await hass.services.async_call("fan", "turn_off", {"entity_id": fan_id}, blocking=True)
    await settle(hass)

    await hass.services.async_call("fan", "turn_on", {"entity_id": fan_id}, blocking=True)
    await settle(hass)

    assert hood.updates[-1]["Fan"]["fanspeed"] == 3


async def test_light_brightness_uses_the_hoods_range_and_the_readback(hass, entry, hood):
    light_id = entity_id(hass, "light", "light")

    await hass.services.async_call("light", "turn_on", {"entity_id": light_id, "brightness": 128}, blocking=True)
    await settle(hass)

    assert hood.updates[-1] == {"Light": {"lightonoff": 1, "lightbrightness": 50}}
    state = hass.states.get(light_id)
    assert state.state == STATE_ON
    assert state.attributes["brightness"] == 128

    await hass.services.async_call("light", "turn_off", {"entity_id": light_id}, blocking=True)
    await settle(hass)
    assert hass.states.get(light_id).state == STATE_OFF


async def test_decolight_keeps_its_colour_across_off_and_on(hass, entry, hood):
    deco_id = entity_id(hass, "light", "decolight")

    await hass.services.async_call("light", "turn_on", {"entity_id": deco_id, "rgb_color": [0, 0, 255]}, blocking=True)
    await settle(hass)
    assert hass.states.get(deco_id).attributes["hs_color"] == (240.0, 100.0)

    await hass.services.async_call("light", "turn_off", {"entity_id": deco_id}, blocking=True)
    await settle(hass)
    await hass.services.async_call("light", "turn_on", {"entity_id": deco_id}, blocking=True)
    await settle(hass)

    payload = hood.updates[-1]["Decolight"]
    assert (payload["decolightr"], payload["decolightg"], payload["decolightb"]) == (0, 0, 255)


async def test_delayed_turn_off_shows_a_timer_and_can_be_cancelled(hass, entry, hood):
    fan_id = entity_id(hass, "fan", "fan")
    timer_id = entity_id(hass, "sensor", "delayed_turn_off_time")
    await hood.notify("Fan", {"fanonoff": 1, "fanspeed": 2})
    await settle(hass)

    await hass.services.async_call(DOMAIN, "start_delayed_off", {"entity_id": fan_id}, blocking=True)
    await settle(hass)

    assert hass.states.get(timer_id).state != "unknown"
    assert hass.states.get(fan_id).attributes["delayed_off_active"] is True
    assert hass.states.get(fan_id).attributes["delayed_off_remaining"] == 5

    await hass.services.async_call(DOMAIN, "cancel_delayed_off", {"entity_id": fan_id}, blocking=True)
    await settle(hass)

    assert hass.states.get(fan_id).attributes["delayed_off_active"] is False
    assert hass.states.get(timer_id).state == "unknown"


async def test_delayed_turn_off_needs_a_running_fan(hass, entry):
    from homeassistant.exceptions import ServiceValidationError

    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            DOMAIN, "start_delayed_off", {"entity_id": entity_id(hass, "fan", "fan")}, blocking=True
        )


async def test_switching_the_fan_off_elsewhere_cancels_the_timer(hass, entry, hood):
    fan_id = entity_id(hass, "fan", "fan")
    await hood.notify("Fan", {"fanonoff": 1, "fanspeed": 2})
    await settle(hass)
    await hass.services.async_call(DOMAIN, "start_delayed_off", {"entity_id": fan_id}, blocking=True)

    await hood.notify("Fan", {"fanonoff": 0, "fanspeed": 0})
    await settle(hass)

    assert hass.states.get(fan_id).attributes["delayed_off_active"] is False


async def test_runtime_is_counted_and_reset_while_running(hass, entry, hood):
    fan_id = entity_id(hass, "fan", "fan")
    await hood.notify("Fan", {"fanonoff": 1, "fanspeed": 2})
    await settle(hass)

    await hass.services.async_call(DOMAIN, "reset_runtime", {"entity_id": fan_id}, blocking=True)
    await settle(hass)

    assert entry.runtime_data.runtime_manager.is_running()  # a running fan keeps being counted
    assert hass.states.get(fan_id).attributes["last_reset"] is not None


async def test_the_open_session_is_saved_when_the_entry_is_unloaded(hass, entry, hood):
    await hood.notify("Fan", {"fanonoff": 1, "fanspeed": 2})
    await settle(hass)
    runtime_manager = entry.runtime_data.runtime_manager
    assert runtime_manager.is_running()

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()

    assert not runtime_manager.is_running()  # closed and saved, nothing is lost
    assert entry.state is ConfigEntryState.NOT_LOADED
    await settle(hass)
    assert all(ws.closed for ws in hood.sockets)


async def test_entities_become_unavailable_when_the_hood_drops_the_connection(hass, entry, hood):
    fan_id = entity_id(hass, "fan", "fan")
    sockets = list(hood.sockets)

    with patch("custom_components.thermex_api.hub.DEFAULT_PORT", 1):  # reconnects fail
        for ws in sockets:
            await ws.close()
        await settle(hass, 0.5)

        assert hass.states.get(fan_id).state == STATE_UNAVAILABLE
        # stored data stays available while the hood is offline
        assert hass.states.get(entity_id(hass, "binary_sensor", "threshold_alert")).state != STATE_UNAVAILABLE


async def test_wrong_password_starts_reauthentication(hass, hood, enable_custom_integrations):
    config_entry = MockConfigEntry(
        domain=DOMAIN, version=2, unique_id=DEVICE_ID,
        data={"host": "127.0.0.1", "api_key": "wrong", "device_id": DEVICE_ID},
    )
    config_entry.add_to_hass(hass)

    assert not await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    assert config_entry.state is ConfigEntryState.SETUP_ERROR
    assert any(flow["context"]["source"] == "reauth" for flow in hass.config_entries.flow.async_progress())


async def test_unreachable_hood_is_retried(hass, enable_custom_integrations):
    config_entry = MockConfigEntry(
        domain=DOMAIN, version=2, unique_id=DEVICE_ID,
        data={"host": "127.0.0.1", "api_key": PASSWORD, "device_id": DEVICE_ID},
    )
    config_entry.add_to_hass(hass)

    with patch("custom_components.thermex_api.hub.DEFAULT_PORT", 1):
        assert not await hass.config_entries.async_setup(config_entry.entry_id)

    assert config_entry.state is ConfigEntryState.SETUP_RETRY
