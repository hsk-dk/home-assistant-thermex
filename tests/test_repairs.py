"""The repair issue for a hood that stays offline."""
from datetime import timedelta
from types import SimpleNamespace

import pytest
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)

from custom_components.thermex_api.const import DOMAIN, OFFLINE_ISSUE_DELAY
from custom_components.thermex_api.repairs import OfflineIssue

AFTER = timedelta(seconds=OFFLINE_ISSUE_DELAY + 1)


@pytest.fixture
def entry(hass):
    entry = MockConfigEntry(domain=DOMAIN, entry_id="e1", data={})
    entry.add_to_hass(hass)
    return entry


@pytest.fixture
def hub():
    return SimpleNamespace(
        available=False,
        connection_state="disconnected",
        availability_signal="thermex_test_availability",
        host="10.0.1.203",
        auth_failed=False,
    )


def issues(hass):
    return list(ir.async_get(hass).issues.values())


async def wait(hass, delta=AFTER):
    async_fire_time_changed(hass, dt_util.utcnow() + delta)
    await hass.async_block_till_done()


def change(hass, hub, state):
    hub.connection_state = state
    hub.available = state == "connected"
    async_dispatcher_send(hass, hub.availability_signal)


async def test_a_hood_that_stays_offline_raises_an_issue_after_a_while(hass, entry, hub):
    OfflineIssue(hass, entry, hub).start()

    await wait(hass, timedelta(seconds=OFFLINE_ISSUE_DELAY - 60))
    assert issues(hass) == []  # a short outage is nothing to act on

    await wait(hass)
    (issue,) = issues(hass)
    assert issue.domain == DOMAIN
    assert issue.issue_id == "hood_offline_e1"
    assert issue.translation_key == "hood_offline"
    assert issue.translation_placeholders == {"host": "10.0.1.203"}
    assert issue.severity is ir.IssueSeverity.WARNING
    assert issue.is_fixable is False


async def test_the_issue_goes_away_when_the_hood_is_back(hass, entry, hub):
    OfflineIssue(hass, entry, hub).start()
    await wait(hass)
    assert len(issues(hass)) == 1

    change(hass, hub, "connected")
    await hass.async_block_till_done()

    assert issues(hass) == []


async def test_a_hood_back_in_time_never_raises_the_issue(hass, entry, hub):
    OfflineIssue(hass, entry, hub).start()

    change(hass, hub, "connected")
    await wait(hass)

    assert issues(hass) == []


async def test_a_hood_that_goes_offline_later_is_watched_too(hass, entry, hub):
    hub.available, hub.connection_state = True, "connected"
    OfflineIssue(hass, entry, hub).start()
    await wait(hass)
    assert issues(hass) == []

    change(hass, hub, "disconnected")
    change(hass, hub, "error")  # more changes while offline do not restart the clock twice
    await wait(hass)

    assert len(issues(hass)) == 1


async def test_a_hood_that_recovered_just_before_the_timer_fires_is_not_reported(hass, entry, hub):
    OfflineIssue(hass, entry, hub).start()

    hub.available, hub.connection_state = True, "connected"  # no signal reached us
    await wait(hass)

    assert issues(hass) == []


async def test_a_closing_hub_is_not_an_outage(hass, entry, hub):
    hub.connection_state = "closed"
    OfflineIssue(hass, entry, hub).start()

    await wait(hass)

    assert issues(hass) == []


async def test_unloading_the_entry_removes_the_issue(hass, entry, hub):
    OfflineIssue(hass, entry, hub).start()
    await wait(hass)
    assert len(issues(hass)) == 1

    await entry._async_process_on_unload(hass)
    await hass.async_block_till_done()

    assert issues(hass) == []
    await wait(hass)
    assert issues(hass) == []  # and nothing is raised afterwards


async def test_a_rejected_password_is_not_reported_as_an_outage(hass, entry, hub):
    hub.auth_failed = True  # the reauthentication flow already asks for a new password
    OfflineIssue(hass, entry, hub).start()

    await wait(hass)

    assert issues(hass) == []


async def test_a_password_rejected_while_the_timer_runs_is_not_reported(hass, entry, hub):
    OfflineIssue(hass, entry, hub).start()

    hub.auth_failed = True
    await wait(hass)

    assert issues(hass) == []
