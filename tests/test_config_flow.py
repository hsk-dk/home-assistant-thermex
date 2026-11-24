"""Config, reauth, reconfigure and options flows, run through Home Assistant's flow manager.

Every flow is driven the way the UI does it (``hass.config_entries.flow`` / ``.options``) and
checked on its terminal result, so the steps, the schemas and the translations are tested together.
"""
import json
import re
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.config_entries import SOURCE_USER
from homeassistant.const import CONF_DEVICE_ID, CONF_HOST
from homeassistant.data_entry_flow import FlowResultType, InvalidData
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.thermex_api import config_flow
from custom_components.thermex_api.config_flow import (
    OPTIONS_SCHEMA,
    STEP_DISCOVERY_DATA_SCHEMA,
    STEP_RECONFIGURE_DATA_SCHEMA,
    STEP_USER_DATA_SCHEMA,
    ConfigFlow,
    OptionsFlowHandler,
)
from custom_components.thermex_api.const import DOMAIN
from custom_components.thermex_api.hub import ThermexAuthError

VALIDATE = "custom_components.thermex_api.config_flow._async_validate_connection"
HUB = "custom_components.thermex_api.config_flow.ThermexHub"
TRANSLATIONS = Path(__file__).parent.parent / "custom_components" / DOMAIN / "translations"


@pytest.fixture(autouse=True)
def _setup(enable_custom_integrations):
    """Never really set an entry up: the flows are what is under test."""
    with patch("custom_components.thermex_api.async_setup_entry", return_value=True), patch(
        "custom_components.thermex_api.async_unload_entry", return_value=True
    ):
        yield


@pytest.fixture
def connects():
    with patch(VALIDATE, return_value=None) as validate:
        yield validate


def make_entry(hass, host="192.168.1.100", title=None, **extra) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        version=2,
        title=title or host,
        unique_id="thermex_abc",
        data={CONF_HOST: host, "api_key": "old", CONF_DEVICE_ID: "thermex_abc"},
        options={"enable_decolight": False},
        **extra,
    )
    entry.add_to_hass(hass)
    return entry


async def start_user(hass):
    return await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})


USER_INPUT = {CONF_HOST: "192.168.1.100", "api_key": "secret", "enable_decolight": False}


# --- user flow ------------------------------------------------------------------------------


async def test_user_flow_shows_the_form(hass):
    result = await start_user(hass)

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"


async def test_user_flow_creates_the_entry(hass, connects):
    result = await start_user(hass)

    result = await hass.config_entries.flow.async_configure(result["flow_id"], USER_INPUT)

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "192.168.1.100"
    assert result["data"][CONF_HOST] == "192.168.1.100"
    assert result["data"]["api_key"] == "secret"
    assert result["options"] == {"enable_decolight": False}
    connects.assert_awaited_once_with(hass, "192.168.1.100", "secret")


async def test_new_entry_gets_a_generated_id_not_the_ip(hass, connects):
    result = await start_user(hass)

    result = await hass.config_entries.flow.async_configure(result["flow_id"], USER_INPUT)

    device_id = result["data"][CONF_DEVICE_ID]
    assert re.fullmatch(r"thermex_[0-9a-f]{12}", device_id)
    assert "192" not in device_id
    assert result["result"].unique_id == device_id


@pytest.mark.parametrize("decolight", [True, False])
async def test_the_decolight_is_chosen_when_the_hood_is_added(hass, connects, decolight):
    result = await start_user(hass)

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {**USER_INPUT, "enable_decolight": decolight}
    )

    assert result["options"] == {"enable_decolight": decolight}
    assert "enable_decolight" not in result["data"]


async def test_the_decolight_is_off_unless_asked_for(hass, connects):
    result = await start_user(hass)

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: "192.168.1.100", "api_key": "secret"}
    )

    assert result["options"] == {"enable_decolight": False}


async def test_the_same_address_cannot_be_added_twice(hass, connects):
    make_entry(hass)
    result = await start_user(hass)

    result = await hass.config_entries.flow.async_configure(result["flow_id"], USER_INPUT)

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    connects.assert_not_called()
    assert len(hass.config_entries.async_entries(DOMAIN)) == 1


@pytest.mark.parametrize("error", ["invalid_auth", "cannot_connect"])
async def test_user_flow_error_can_be_corrected(hass, error):
    result = await start_user(hass)

    with patch(VALIDATE, return_value=error):
        result = await hass.config_entries.flow.async_configure(result["flow_id"], USER_INPUT)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    assert result["errors"] == {"base": error}

    with patch(VALIDATE, return_value=None):
        result = await hass.config_entries.flow.async_configure(result["flow_id"], USER_INPUT)
    assert result["type"] is FlowResultType.CREATE_ENTRY


# --- the connection test ----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("connect", "expected"),
    [
        (None, None),
        (ThermexAuthError("rejected"), "invalid_auth"),
        (OSError("unreachable"), "cannot_connect"),
        (TimeoutError(), "cannot_connect"),
    ],
)
async def test_validate_connection_maps_errors_and_always_closes_the_hub(hass, connect, expected):
    with patch(f"{HUB}.connect", AsyncMock(side_effect=connect)), patch(
        f"{HUB}.close", AsyncMock()
    ) as close:
        assert await config_flow._async_validate_connection(hass, "h", "k") == expected

    close.assert_awaited_once()


async def test_a_failing_close_does_not_hide_the_result(hass):
    with patch(f"{HUB}.connect", AsyncMock()), patch(
        f"{HUB}.close", AsyncMock(side_effect=RuntimeError("boom"))
    ):
        assert await config_flow._async_validate_connection(hass, "h", "k") is None

    with patch(f"{HUB}.connect", AsyncMock(side_effect=ThermexAuthError("x"))), patch(
        f"{HUB}.close", AsyncMock(side_effect=RuntimeError("boom"))
    ):
        assert await config_flow._async_validate_connection(hass, "h", "k") == "invalid_auth"


# --- reauth ----------------------------------------------------------------------------------


async def test_reauth_asks_for_the_password_and_updates_it(hass, connects):
    entry = make_entry(hass)

    result = await entry.start_reauth_flow(hass)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reauth_confirm"
    assert result["description_placeholders"]["host"] == "192.168.1.100"

    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"api_key": "new"})

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert entry.data["api_key"] == "new"
    assert entry.data[CONF_HOST] == "192.168.1.100"
    connects.assert_awaited_once_with(hass, "192.168.1.100", "new")


@pytest.mark.parametrize("error", ["invalid_auth", "cannot_connect"])
async def test_reauth_error_can_be_corrected(hass, error):
    entry = make_entry(hass)
    result = await entry.start_reauth_flow(hass)

    with patch(VALIDATE, return_value=error):
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {"api_key": "bad"})
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reauth_confirm"
    assert result["errors"] == {"base": error}
    assert entry.data["api_key"] == "old"

    with patch(VALIDATE, return_value=None):
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {"api_key": "good"})
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert entry.data["api_key"] == "good"


# --- reconfigure -----------------------------------------------------------------------------


async def test_reconfigure_form_is_prefilled(hass):
    entry = make_entry(hass)

    result = await entry.start_reconfigure_flow(hass)

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reconfigure"
    (host,) = [k for k in result["data_schema"].schema if str(k) == "host"]
    assert host.description == {"suggested_value": "192.168.1.100"}


async def test_reconfigure_updates_host_and_password_and_the_title_follows(hass, connects):
    entry = make_entry(hass)
    result = await entry.start_reconfigure_flow(hass)

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"host": "192.168.1.200", "api_key": "new"}
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert entry.data["host"] == "192.168.1.200"
    assert entry.data["api_key"] == "new"
    assert entry.data[CONF_DEVICE_ID] == "thermex_abc"  # the identity never changes
    assert entry.title == "192.168.1.200"
    connects.assert_awaited_once_with(hass, "192.168.1.200", "new")


async def test_reconfigure_keeps_a_title_the_user_chose(hass, connects):
    entry = make_entry(hass, title="Kitchen hood")
    result = await entry.start_reconfigure_flow(hass)

    await hass.config_entries.flow.async_configure(
        result["flow_id"], {"host": "192.168.1.200", "api_key": "k"}
    )

    assert entry.title == "Kitchen hood"
    assert entry.data["host"] == "192.168.1.200"


async def test_reconfigure_allows_the_same_host_for_a_password_change(hass, connects):
    entry = make_entry(hass)
    result = await entry.start_reconfigure_flow(hass)

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"host": "192.168.1.100", "api_key": "new"}
    )

    assert result["reason"] == "reconfigure_successful"
    assert entry.data["api_key"] == "new"


async def test_reconfigure_rejects_a_host_used_by_another_hood(hass, connects):
    entry = make_entry(hass)
    other = MockConfigEntry(
        domain=DOMAIN, unique_id="thermex_other", data={CONF_HOST: "192.168.1.201", "api_key": "k"}
    )
    other.add_to_hass(hass)
    result = await entry.start_reconfigure_flow(hass)

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"host": "192.168.1.201", "api_key": "k"}
    )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "host_in_use"}
    assert entry.data["host"] == "192.168.1.100"
    connects.assert_not_called()


@pytest.mark.parametrize("error", ["invalid_auth", "cannot_connect"])
async def test_reconfigure_error_can_be_corrected(hass, error):
    entry = make_entry(hass)
    result = await entry.start_reconfigure_flow(hass)

    with patch(VALIDATE, return_value=error):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"host": "192.168.1.250", "api_key": "k"}
        )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": error}
    assert entry.data["host"] == "192.168.1.100"

    with patch(VALIDATE, return_value=None):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"host": "192.168.1.250", "api_key": "k"}
        )
    assert result["reason"] == "reconfigure_successful"
    assert entry.data["host"] == "192.168.1.250"


# --- options ---------------------------------------------------------------------------------


async def test_options_flow_shows_the_current_values_and_saves_changes(hass):
    entry = make_entry(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "init"

    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            "enable_decolight": True,
            "fan_alert_hours": 120,
            "fan_alert_days": 100,
            "fan_auto_off_delay": 30,
        },
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options == {
        "enable_decolight": True,
        "fan_alert_hours": 120,
        "fan_alert_days": 100,
        "fan_auto_off_delay": 30,
    }


async def test_options_flow_rejects_values_out_of_range(hass):
    entry = make_entry(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)

    with pytest.raises(InvalidData):
        await hass.config_entries.options.async_configure(
            result["flow_id"], {"fan_alert_hours": 0}
        )


def test_options_flow_reloads_the_entry_automatically():
    from homeassistant.config_entries import OptionsFlowWithReload

    assert issubclass(OptionsFlowHandler, OptionsFlowWithReload)
    assert isinstance(ConfigFlow.async_get_options_flow(None), OptionsFlowHandler)


# --- schemas and translations ----------------------------------------------------------------


def test_the_decolight_schema_defaults_to_off():
    assert STEP_USER_DATA_SCHEMA({CONF_HOST: "h", "api_key": "k"})["enable_decolight"] is False


def test_reconfigure_does_not_ask_for_the_decolight():
    assert "enable_decolight" not in {str(k) for k in STEP_RECONFIGURE_DATA_SCHEMA.schema}


def schema_fields():
    """(step path, field names) of every form of the config and options flows."""
    return {
        ("config", "user"): STEP_USER_DATA_SCHEMA,
        ("config", "discovery_confirm"): STEP_DISCOVERY_DATA_SCHEMA,
        ("config", "reconfigure"): STEP_RECONFIGURE_DATA_SCHEMA,
        ("options", "init"): OPTIONS_SCHEMA,
    }


@pytest.mark.parametrize("language", sorted(p.stem for p in TRANSLATIONS.glob("*.json")))
def test_every_field_is_labelled_and_explained(language):
    translations = json.loads((TRANSLATIONS / f"{language}.json").read_text(encoding="utf-8"))

    for (section, step), schema in schema_fields().items():
        fields = {str(key) for key in schema.schema}
        texts = translations[section]["step"][step]
        assert set(texts["data"]) == fields, (section, step)
        assert set(texts["data_description"]) == fields, (section, step)
    reauth = translations["config"]["step"]["reauth_confirm"]
    assert set(reauth["data"]) == set(reauth["data_description"]) == {"api_key"}
