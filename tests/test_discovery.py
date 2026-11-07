"""Discovery: a device named Thermex-ESP appears in DHCP (the real flow in a real Home Assistant)."""
import json
from pathlib import Path
from unittest.mock import patch

import pytest
from homeassistant.config_entries import SOURCE_DHCP, SOURCE_IGNORE
from homeassistant.const import CONF_DEVICE_ID, CONF_HOST, CONF_MAC
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers.service_info.dhcp import DhcpServiceInfo
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.thermex_api.const import DOMAIN

MAC = "441793aabbcc"
FORMATTED = "44:17:93:aa:bb:cc"
COMPONENT = Path(__file__).parent.parent / "custom_components" / DOMAIN


@pytest.fixture(autouse=True)
def _setup(enable_custom_integrations):
    with patch("custom_components.thermex_api.async_setup_entry", return_value=True) as setup:
        yield setup


@pytest.fixture
def connects():
    with patch(
        "custom_components.thermex_api.config_flow._async_validate_connection", return_value=None
    ) as validate:
        yield validate


def seen(ip: str = "10.0.1.203", mac: str = MAC) -> DhcpServiceInfo:
    return DhcpServiceInfo(ip=ip, hostname="thermex-esp", macaddress=mac)


async def discover(hass, info: DhcpServiceInfo):
    return await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_DHCP}, data=info
    )


def existing(hass, host="10.0.1.203", mac=None) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        version=2,
        unique_id="thermex_abc",
        data={CONF_HOST: host, "api_key": "k", CONF_DEVICE_ID: "thermex_abc", **({CONF_MAC: mac} if mac else {})},
    )
    entry.add_to_hass(hass)
    return entry


def test_the_manifest_matches_the_hoods_hostname():
    manifest = json.loads((COMPONENT / "manifest.json").read_text(encoding="utf-8"))

    assert manifest["dhcp"] == [{"hostname": "thermex-esp*"}]


async def test_a_new_hood_asks_for_the_password_and_is_created(hass, connects):
    result = await discover(hass, seen())

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "discovery_confirm"
    assert result["description_placeholders"] == {"host": "10.0.1.203"}

    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"api_key": "secret"})

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "10.0.1.203"
    assert result["data"][CONF_HOST] == "10.0.1.203"
    assert result["data"]["api_key"] == "secret"
    assert result["data"][CONF_MAC] == FORMATTED
    assert result["data"][CONF_DEVICE_ID].startswith("thermex_")
    assert "203" not in result["data"][CONF_DEVICE_ID]
    connects.assert_awaited_once_with(hass, "10.0.1.203", "secret")


@pytest.mark.parametrize("error", ["invalid_auth", "cannot_connect"])
async def test_a_wrong_password_can_be_corrected(hass, error):
    result = await discover(hass, seen())

    with patch("custom_components.thermex_api.config_flow._async_validate_connection", return_value=error):
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {"api_key": "bad"})
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": error}

    with patch("custom_components.thermex_api.config_flow._async_validate_connection", return_value=None):
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {"api_key": "good"})
    assert result["type"] is FlowResultType.CREATE_ENTRY


async def test_the_same_hood_seen_twice_has_one_flow(hass):
    await discover(hass, seen())

    result = await discover(hass, seen())

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_in_progress"


async def test_a_hood_added_by_hand_learns_its_mac_and_is_not_offered(hass):
    entry = existing(hass)

    result = await discover(hass, seen())

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    assert entry.data[CONF_MAC] == FORMATTED
    assert entry.data[CONF_HOST] == "10.0.1.203"


async def test_a_new_ip_address_from_the_router_is_followed(hass):
    entry = existing(hass, host="10.0.1.203", mac=FORMATTED)

    with patch("custom_components.thermex_api.async_setup_entry", return_value=True) as setup, \
            patch("custom_components.thermex_api.async_unload_entry", return_value=True):
        await hass.config_entries.async_setup(entry.entry_id)
        setup.reset_mock()
        result = await discover(hass, seen(ip="10.0.1.77"))
        await hass.async_block_till_done()

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    assert entry.data[CONF_HOST] == "10.0.1.77"
    setup.assert_awaited_once()  # reloaded with the new address


async def test_an_unchanged_hood_is_not_reloaded(hass):
    entry = existing(hass, host="10.0.1.203", mac=FORMATTED)

    with patch.object(hass.config_entries, "async_schedule_reload") as reload:
        result = await discover(hass, seen())

    assert result["reason"] == "already_configured"
    reload.assert_not_called()
    assert entry.data[CONF_HOST] == "10.0.1.203"


async def test_another_device_on_a_known_address_is_not_taken_for_the_hood(hass, connects):
    """The address of a hood whose MAC we know now belongs to something else."""
    existing(hass, host="10.0.1.203", mac="44:17:93:00:00:01")

    result = await discover(hass, seen(mac="441793000002"))

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "discovery_confirm"


async def test_an_ignored_hood_is_not_offered_again(hass):
    MockConfigEntry(domain=DOMAIN, unique_id=FORMATTED, source=SOURCE_IGNORE, data={}).add_to_hass(hass)

    result = await discover(hass, seen())

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_the_discovery_is_titled_with_the_address(hass):
    await discover(hass, seen())

    (flow,) = hass.config_entries.flow.async_progress_by_handler(DOMAIN)
    assert flow["context"]["title_placeholders"] == {"host": "10.0.1.203"}
    assert flow["context"]["unique_id"] == FORMATTED


def test_every_language_has_the_discovery_texts():
    for path in sorted((COMPONENT / "translations").glob("*.json")):
        config = json.loads(path.read_text(encoding="utf-8"))["config"]

        assert {"title", "description", "data"} <= config["step"]["discovery_confirm"].keys(), path.name
        assert "{host}" in config["step"]["discovery_confirm"]["description"], path.name
        assert "{host}" in config["flow_title"], path.name
        assert config["abort"]["already_in_progress"], path.name
