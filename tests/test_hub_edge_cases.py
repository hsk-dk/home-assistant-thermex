"""ThermexHub: the rare paths (races while reconnecting, odd replies, failing sockets)."""
import asyncio
import contextlib
import json
import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiohttp import WSMsgType

from custom_components.thermex_api.hub import ThermexHub

HUB = "custom_components.thermex_api.hub"


@pytest.fixture
def hub(event_loop):
    hass = MagicMock()
    hass.loop = event_loop
    hass.async_create_background_task = MagicMock(side_effect=lambda coro, name=None: coro.close())
    return ThermexHub(hass, "192.168.1.100", "pw", "entry")


def open_ws():
    ws = MagicMock()
    ws.closed = False
    ws.close = AsyncMock()
    ws.send_json = AsyncMock()
    return ws


class HookLock:
    """Stands in for an asyncio.Lock and runs a hook the n-th time it is entered."""

    def __init__(self, hooks=None):
        self.entered = 0
        self.hooks = hooks or {}

    def locked(self):
        return False

    async def __aenter__(self):
        self.entered += 1
        if hook := self.hooks.get(self.entered):
            hook()

    async def __aexit__(self, *exc):
        return False


# --- reconnecting -------------------------------------------------------------------------------


async def test_a_task_that_finds_a_reconnect_running_waits_for_it(hub):
    await hub._reconnect_lock.acquire()
    try:
        with patch.object(hub, "_wait_for_reconnection", AsyncMock()) as wait, patch.object(
            hub, "_perform_reconnection", AsyncMock()
        ) as perform:
            await hub._ensure_connected()
    finally:
        hub._reconnect_lock.release()

    wait.assert_awaited_once()
    perform.assert_not_called()


async def test_closing_while_waiting_for_the_reconnect_lock_stops(hub):
    hub._reconnect_lock = HookLock({1: lambda: setattr(hub, "_closing", True)})

    with patch.object(hub, "_perform_reconnection", AsyncMock()) as perform:
        with pytest.raises(ConnectionError, match="closing"):
            await hub._ensure_connected()

    perform.assert_not_called()


async def test_a_reconnect_done_by_another_task_is_not_repeated(hub):
    hub._reconnect_lock = HookLock({1: lambda: setattr(hub, "_ws", open_ws())})

    with patch.object(hub, "_perform_reconnection", AsyncMock()) as perform:
        await hub._ensure_connected()

    perform.assert_not_called()


async def test_a_waiter_is_released_when_the_other_reconnect_succeeds(hub):
    waiter = asyncio.create_task(hub._wait_for_reconnection())
    await asyncio.sleep(0)
    hub._ws = open_ws()
    hub._reconnect_event.set()

    await asyncio.wait_for(waiter, 1)  # returns without raising


async def test_closing_during_the_retries_stops_reconnecting(hub):
    async def close_while_closing_connection():
        hub._closing = True

    with patch.object(hub, "_close_connection", close_while_closing_connection), patch.object(
        hub, "connect", AsyncMock()
    ) as connect:
        with pytest.raises(ConnectionError, match="closing during reconnection"):
            await hub._perform_reconnection()

    connect.assert_not_called()


async def test_an_old_receive_loop_is_cancelled_before_a_new_connection(hub):
    old = asyncio.create_task(asyncio.sleep(3600))
    hub._recv_task = old

    await hub._cancel_recv_task()

    assert old.cancelled()
    assert hub._recv_task is None


async def test_dead_connection_that_cannot_be_reopened_is_left_to_the_watchdog(hub, caplog):
    with patch.object(hub, "_ensure_connected", AsyncMock(side_effect=ConnectionError("down"))):
        with caplog.at_level(logging.DEBUG, logger=HUB):
            await hub._reconnect_dead_connection("silent")  # must not raise

    assert hub.last_error == "silent"
    assert hub.connection_state == "disconnected"
    assert any("Reconnecting a dead connection failed" in r.getMessage() for r in caplog.records)


# --- the protocol version -----------------------------------------------------------------------


async def connect_with(hub, protocol):
    """Connect with a hood that accepts the password and answers the version request as given."""
    ws = open_ws()
    ws.receive = AsyncMock(
        return_value=MagicMock(type=WSMsgType.TEXT, data=json.dumps({"Response": "Authenticate", "Status": 200}))
    )
    session = MagicMock()
    session.ws_connect = AsyncMock(return_value=ws)
    request = AsyncMock(side_effect=protocol) if isinstance(protocol, BaseException) else AsyncMock(return_value=protocol)
    with patch(f"{HUB}.async_get_clientsession", return_value=session), patch.object(hub, "send_request", request):
        await hub.connect()


@pytest.mark.parametrize(
    ("data", "expected"),
    [
        ({"Version": "1.2"}, "1.2"),
        ({"MajorVersion": 2, "MinorVersion": 3}, "2.3"),
        ({"something": "else"}, "unknown"),
    ],
)
async def test_the_protocol_version_is_read_in_every_format(hub, data, expected):
    await connect_with(hub, {"Status": 200, "Data": data})

    assert hub.protocol_version == expected
    assert hub.available


async def test_a_refused_version_request_does_not_stop_the_connection(hub, caplog):
    with caplog.at_level(logging.ERROR, logger=HUB):
        await connect_with(hub, {"Status": 400})

    assert hub.protocol_version is None
    assert hub.available
    assert any("non-200" in r.getMessage() for r in caplog.records)


async def test_no_answer_to_the_version_request_is_not_an_error(hub, caplog):
    with caplog.at_level(logging.ERROR, logger=HUB):
        await connect_with(hub, TimeoutError())

    assert hub.protocol_version is None
    assert hub.available
    assert caplog.records == []


async def test_a_failing_version_request_is_noted_but_the_hood_stays_connected(hub):
    await connect_with(hub, ValueError("garbled"))

    assert hub.available
    assert hub.last_error == "ProtocolVersion request failed: garbled"


# --- the receive loop ---------------------------------------------------------------------------


def stream(*messages, then=None):
    async def gen():
        for message in messages:
            yield message
        if then:
            raise then

    ws = MagicMock()
    ws.closed = True
    ws.close_code = 1000
    ws.exception = MagicMock(return_value=None)
    ws.__aiter__ = lambda self: gen().__aiter__()
    return ws


async def test_an_unreadable_message_is_noted_and_the_loop_goes_on(hub):
    bad = MagicMock(type=WSMsgType.TEXT, data="{not json")
    good = MagicMock(type=WSMsgType.TEXT, data=json.dumps({"Notify": "x", "Data": {"a": 1}}))
    hub._ws = stream(bad, good)

    with patch(f"{HUB}.async_dispatcher_send") as send:
        await hub._recv_loop()

    send.assert_any_call(hub._hass, hub.signal, {"a": 1})  # the next message still got through


async def test_a_failing_stream_records_why(hub):
    hub._ws = stream(then=RuntimeError("socket exploded"))

    with patch(f"{HUB}.async_dispatcher_send"):
        await hub._recv_loop()

    assert hub.last_error == "Receive loop error: socket exploded"
    assert hub.connection_state == "disconnected"


# --- the watchdog -------------------------------------------------------------------------------


@contextlib.asynccontextmanager
async def running_watchdog(hub, seconds=0.15):
    hub._heartbeat_interval = 0.02
    hub._last_activity = asyncio.get_event_loop().time()
    task = asyncio.create_task(hub._watchdog_loop())
    try:
        yield task
        await asyncio.sleep(seconds)
    finally:
        hub._closing = True
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task


async def test_watchdog_survives_a_failed_reconnect(hub, caplog):
    hub._ws = None
    with patch.object(hub, "_ensure_connected", AsyncMock(side_effect=ConnectionError("down"))) as ensure:
        with caplog.at_level(logging.DEBUG, logger=HUB):
            async with running_watchdog(hub):
                pass

    assert ensure.await_count >= 2  # it kept trying
    assert any("Watchdog reconnection failed" in r.getMessage() for r in caplog.records)


async def test_a_heartbeat_that_fails_on_the_connection_does_not_reconnect(hub, caplog):
    hub._ws = open_ws()
    with patch.object(hub, "send_request", AsyncMock(side_effect=ConnectionError("gone"))) as request, patch.object(
        hub, "_reconnect_dead_connection", AsyncMock()
    ) as reconnect:
        with caplog.at_level(logging.DEBUG, logger=HUB):
            async with running_watchdog(hub):
                pass

    assert request.await_count >= 1
    reconnect.assert_not_called()
    assert any("Heartbeat failed due to connection" in r.getMessage() for r in caplog.records)


async def test_an_unexpected_error_is_logged_and_the_watchdog_pauses(hub, caplog):
    hub._reconnect_lock = MagicMock(locked=MagicMock(side_effect=RuntimeError("boom")))

    with caplog.at_level(logging.ERROR, logger=HUB):
        async with running_watchdog(hub):
            pass  # it is paused in its 5 s back-off when the helper cancels it

    assert any("Watchdog loop error: boom" in r.getMessage() for r in caplog.records)


# --- sending requests ---------------------------------------------------------------------------


@pytest.fixture
def sending(hub):
    """A hub that is connected; requests go to hub._ws.send_json."""
    hub._ws = open_ws()
    with patch.object(hub, "_ensure_connected", AsyncMock()), patch(f"{HUB}.WEBSOCKET_REQUEST_TIMEOUT", 0.05):
        yield hub


async def test_nothing_is_sent_once_the_hub_is_closing(hub):
    hub._closing = True

    with pytest.raises(ConnectionError, match="closing"):
        await hub._send_request("status", {})


async def test_a_request_of_the_same_type_replaces_a_stuck_one(sending, caplog):
    hub = sending
    stuck = asyncio.get_event_loop().create_future()
    hub._pending["status"] = stuck

    async def answer(payload):
        hub._pending["status"].set_result({"Response": "Status"})

    hub._ws.send_json = AsyncMock(side_effect=answer)
    with caplog.at_level(logging.WARNING, logger=HUB):
        assert await hub._send_request("status", {}) == {"Response": "Status"}

    assert any("Overwriting pending request" in r.getMessage() for r in caplog.records)
    assert hub._pending == {}


async def test_closing_after_the_connection_check_sends_nothing(sending):
    hub = sending
    hub._ensure_connected = AsyncMock(side_effect=lambda: setattr(hub, "_closing", True))

    with pytest.raises(ConnectionError, match="closing"):
        await hub._send_request("status", {})

    hub._ws.send_json.assert_not_called()
    assert hub._pending == {}


async def test_a_socket_lost_before_sending_is_reported(sending):
    hub = sending
    hub._ws = None

    with pytest.raises(ConnectionError, match="lost before sending"):
        await hub._send_request("status", {})

    assert hub._pending == {}


async def test_a_failing_send_is_reported(sending):
    hub = sending
    hub._ws.send_json = AsyncMock(side_effect=OSError("broken pipe"))

    with pytest.raises(ConnectionError, match=r"Failed to send.*broken pipe"):
        await hub._send_request("status", {})

    assert hub._pending == {}


async def test_closing_while_waiting_for_the_first_answer_stops_the_retry(sending):
    hub = sending
    hub._ws.send_json = AsyncMock(side_effect=lambda payload: setattr(hub, "_closing", True))

    with pytest.raises(ConnectionError, match="closing"):
        await hub._send_request("status", {})

    assert hub._ws.send_json.await_count == 1  # no second send
    assert hub._pending == {}


async def test_closing_before_the_retry_is_sent(sending):
    hub = sending
    hub._ws_lock = HookLock({2: lambda: setattr(hub, "_closing", True)})

    with pytest.raises(ConnectionError, match="closing"):
        await hub._send_request("status", {})

    assert hub._ws.send_json.await_count == 1
    assert hub._pending == {}


async def test_a_socket_lost_before_the_retry_is_reported(sending):
    hub = sending
    hub._ws_lock = HookLock({2: lambda: setattr(hub, "_ws", None)})

    with pytest.raises(ConnectionError, match="lost during retry"):
        await hub._send_request("status", {})

    assert hub._pending == {}


async def test_a_failing_retry_is_reported(sending):
    hub = sending
    hub._ws.send_json = AsyncMock(side_effect=[None, OSError("reset")])

    with pytest.raises(ConnectionError, match=r"Failed to retry.*reset"):
        await hub._send_request("status", {})

    assert hub._pending == {}


async def test_two_timeouts_give_up_after_one_retry(sending):
    hub = sending

    with pytest.raises(TimeoutError, match="2 attempts"):
        await hub._send_request("status", {})

    assert hub._ws.send_json.await_count == 2
    assert hub._pending == {}


async def test_a_late_answer_to_the_retry_is_accepted(sending):
    hub = sending
    calls = 0

    async def answer_second_time(payload):
        nonlocal calls
        calls += 1
        if calls == 2:
            hub._pending["status"].set_result({"Response": "Status", "Data": {}})

    hub._ws.send_json = AsyncMock(side_effect=answer_second_time)

    assert await hub._send_request("status", {}) == {"Response": "Status", "Data": {}}


# --- reading a rejected fan update back ---------------------------------------------------------


@pytest.mark.parametrize("fan_state", [None, "on", ["x"]])
async def test_a_status_without_fan_details_does_not_count_as_applied(hub, fan_state):
    hub.send_request = AsyncMock(return_value={"Data": {"Fan": fan_state}})

    assert await hub._fan_update_applied({"Fan": {"fanonoff": 1}}) is False



async def test_an_update_carries_its_data_but_a_status_request_does_not(sending):
    hub = sending
    sent = []

    async def answer(payload):
        sent.append(payload)
        hub._pending[payload["Request"].lower()].set_result({"Status": 200})

    hub._ws.send_json = AsyncMock(side_effect=answer)

    await hub._send_request("Update", {"Light": {"lightonoff": 1}})
    await hub._send_request("status", {})

    assert sent == [{"Request": "Update", "Data": {"Light": {"lightonoff": 1}}}, {"Request": "Status"}]
