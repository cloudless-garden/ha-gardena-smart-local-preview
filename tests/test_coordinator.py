# SPDX-FileCopyrightText: 2026 GARDENA GmbH
#
# SPDX-License-Identifier: Apache-2.0

"""Tests for the GARDENA smart local websocket coordinator."""

from __future__ import annotations

import asyncio
import logging
from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp
import pytest
from homeassistant.core import HomeAssistant

from custom_components.gardena_smart_local_preview import (
    coordinator as coordinator_module,
)
from custom_components.gardena_smart_local_preview.coordinator import (
    GardenaSmartLocalCoordinator,
    IncludableDeviceInfo,
)
from gardena_smart_local_api.devices import DeviceMap
from gardena_smart_local_api.messages import (
    Entity,
    Event,
    IngressMessageList,
    Reply,
)
from gardena_smart_local_api.resources import IpsoPath

PATCH_CLIENTSESSION = (
    "custom_components.gardena_smart_local_preview.coordinator.async_get_clientsession"
)


async def _pump() -> None:
    """Let pending coroutines/background tasks progress."""
    await asyncio.sleep(0.05)


def _session_with(ws_side_effect) -> MagicMock:
    session = MagicMock()
    session.ws_connect = MagicMock(side_effect=ws_side_effect)
    return session


def _includable_event(
    instance_id: str = "instance-1",
    op: str = "update",
    service: str | None = "some-service",
    identifier: str | None = "ABCDEF0123456789ABCDEF01",
) -> Event:
    payload = {"identifier": {"vs": identifier}} if identifier is not None else {}
    return Event(
        op=op,
        payload=payload,
        entity=Entity(
            service=service,
            path=IpsoPath(
                object_name="includable_device", object_instance_id=instance_id
            ),
        ),
    )


async def test_async_update_data_returns_devices(
    coordinator: GardenaSmartLocalCoordinator, mock_device
) -> None:
    coordinator._devices["device-1"] = mock_device(device_id="device-1")
    assert await coordinator._async_update_data() is coordinator._devices


# ---------------------------------------------------------------------------
# Connection lifecycle: async_connect / _ws_loop / async_disconnect
# ---------------------------------------------------------------------------


async def test_async_connect_sets_up_task_and_ssl_context(
    hass: HomeAssistant, coordinator: GardenaSmartLocalCoordinator, fake_ws
) -> None:
    coordinator._do_discovery = AsyncMock()
    ws = fake_ws()
    session = _session_with([ws])

    with patch(PATCH_CLIENTSESSION, return_value=session):
        await coordinator.async_connect()
        await _pump()

        assert coordinator._task is not None
        assert coordinator._ssl_context is not None
        coordinator._do_discovery.assert_awaited_once()
        assert coordinator._ws is ws

    await coordinator.async_disconnect()
    assert coordinator._ws is None
    assert coordinator._pending_replies == {}


async def test_ws_loop_reconnects_after_reader_exit(
    hass: HomeAssistant,
    coordinator: GardenaSmartLocalCoordinator,
    fake_ws,
    caplog: pytest.LogCaptureFixture,
) -> None:
    coordinator._do_discovery = AsyncMock()
    closed_ws = fake_ws(
        messages=[aiohttp.WSMessage(aiohttp.WSMsgType.CLOSED, None, None)]
    )
    session = _session_with([closed_ws, asyncio.CancelledError()])

    with (
        patch(PATCH_CLIENTSESSION, return_value=session),
        caplog.at_level(logging.INFO),
    ):
        await coordinator.async_connect()
        await _pump()

    assert session.ws_connect.call_count == 2
    assert "Disconnected from GARDENA smart Gateway, reconnecting" in caplog.text
    assert coordinator._task.done()


async def test_ws_loop_reconnects_after_exception(
    hass: HomeAssistant,
    coordinator: GardenaSmartLocalCoordinator,
    fake_ws,
    caplog: pytest.LogCaptureFixture,
) -> None:
    coordinator._do_discovery = AsyncMock()
    session = _session_with(
        [aiohttp.ClientConnectionError("boom"), asyncio.CancelledError()]
    )
    sleep_calls: list[float] = []
    real_sleep = asyncio.sleep

    async def fake_sleep(delay: float) -> None:
        sleep_calls.append(delay)

    with (
        patch(PATCH_CLIENTSESSION, return_value=session),
        patch.object(coordinator_module.asyncio, "sleep", fake_sleep),
        caplog.at_level(logging.ERROR),
    ):
        await coordinator.async_connect()
        await real_sleep(0.05)

    assert sleep_calls == [5]
    assert "WebSocket error: boom" in caplog.text
    assert session.ws_connect.call_count == 2


async def test_ws_loop_401_starts_reauth_and_stops_retrying(
    hass: HomeAssistant,
    coordinator: GardenaSmartLocalCoordinator,
    caplog: pytest.LogCaptureFixture,
) -> None:
    coordinator.config_entry = MagicMock()
    session = _session_with(
        [
            aiohttp.WSServerHandshakeError(
                request_info=MagicMock(), history=(), status=401, message="Unauthorized"
            )
        ]
    )

    with (
        patch(PATCH_CLIENTSESSION, return_value=session),
        caplog.at_level(logging.ERROR),
    ):
        await coordinator.async_connect()
        await _pump()

    assert session.ws_connect.call_count == 1
    coordinator.config_entry.async_start_reauth.assert_called_once_with(hass)
    assert "Authentication failed" in caplog.text
    assert coordinator._task.done()


async def test_ws_loop_non_401_handshake_error_reconnects(
    hass: HomeAssistant,
    coordinator: GardenaSmartLocalCoordinator,
    caplog: pytest.LogCaptureFixture,
) -> None:
    coordinator.config_entry = MagicMock()
    session = _session_with(
        [
            aiohttp.WSServerHandshakeError(
                request_info=MagicMock(),
                history=(),
                status=500,
                message="Server error",
            ),
            asyncio.CancelledError(),
        ]
    )
    sleep_calls: list[float] = []
    real_sleep = asyncio.sleep

    async def fake_sleep(delay: float) -> None:
        sleep_calls.append(delay)

    with (
        patch(PATCH_CLIENTSESSION, return_value=session),
        patch.object(coordinator_module.asyncio, "sleep", fake_sleep),
        caplog.at_level(logging.ERROR),
    ):
        await coordinator.async_connect()
        await real_sleep(0.05)

    assert sleep_calls == [5]
    assert session.ws_connect.call_count == 2
    coordinator.config_entry.async_start_reauth.assert_not_called()


async def test_ws_loop_cancelled_on_connect_breaks_cleanly(
    hass: HomeAssistant,
    coordinator: GardenaSmartLocalCoordinator,
    caplog: pytest.LogCaptureFixture,
) -> None:
    session = _session_with([asyncio.CancelledError()])

    with (
        patch(PATCH_CLIENTSESSION, return_value=session),
        caplog.at_level(logging.ERROR),
    ):
        await coordinator.async_connect()
        await _pump()

    assert coordinator._task.done()
    assert "WebSocket error" not in caplog.text


async def test_async_disconnect_noop_when_never_connected(
    hass: HomeAssistant, coordinator: GardenaSmartLocalCoordinator
) -> None:
    assert coordinator._task is None
    await coordinator.async_disconnect()


async def test_ws_loop_finally_cancels_pending_reply_futures(
    hass: HomeAssistant,
    coordinator: GardenaSmartLocalCoordinator,
    fake_ws,
) -> None:
    coordinator._do_discovery = AsyncMock()
    ws = fake_ws()
    session = _session_with([ws, asyncio.CancelledError()])

    with patch(PATCH_CLIENTSESSION, return_value=session):
        await coordinator.async_connect()
        await _pump()

        loop = asyncio.get_running_loop()
        pending = loop.create_future()
        coordinator._pending_replies["req-1"] = pending

        ws.simulate_close()
        await _pump()

    assert pending.cancelled()
    assert coordinator._pending_replies == {}


async def test_async_disconnect_cancels_includable_timers(
    hass: HomeAssistant, coordinator: GardenaSmartLocalCoordinator
) -> None:
    handle = MagicMock()
    coordinator._includable_timeouts["instance-1"] = handle

    await coordinator.async_disconnect()

    handle.cancel.assert_called_once()
    assert coordinator._includable_timeouts == {}


# ---------------------------------------------------------------------------
# _ws_reader
# ---------------------------------------------------------------------------


async def test_ws_reader_text_message_queued(
    coordinator: GardenaSmartLocalCoordinator, fake_ws
) -> None:
    ws = fake_ws(
        messages=[
            aiohttp.WSMessage(aiohttp.WSMsgType.TEXT, "hello", None),
            aiohttp.WSMessage(aiohttp.WSMsgType.CLOSED, None, None),
        ]
    )
    await coordinator._ws_reader(ws)
    assert coordinator._msg_queue.get_nowait() == "hello"


async def test_ws_reader_binary_message_decoded_and_queued(
    coordinator: GardenaSmartLocalCoordinator, fake_ws
) -> None:
    ws = fake_ws(
        messages=[
            aiohttp.WSMessage(aiohttp.WSMsgType.BINARY, b"hello", None),
            aiohttp.WSMessage(aiohttp.WSMsgType.CLOSED, None, None),
        ]
    )
    await coordinator._ws_reader(ws)
    assert coordinator._msg_queue.get_nowait() == "hello"


async def test_ws_reader_error_breaks_and_logs(
    coordinator: GardenaSmartLocalCoordinator,
    fake_ws,
    caplog: pytest.LogCaptureFixture,
) -> None:
    ws = fake_ws(messages=[aiohttp.WSMessage(aiohttp.WSMsgType.ERROR, None, None)])
    ws._exception = RuntimeError("socket broke")

    with caplog.at_level(logging.ERROR):
        await coordinator._ws_reader(ws)

    assert coordinator._msg_queue.empty()
    assert "socket broke" in caplog.text


async def test_ws_reader_closed_breaks(
    coordinator: GardenaSmartLocalCoordinator,
    fake_ws,
    caplog: pytest.LogCaptureFixture,
) -> None:
    ws = fake_ws(messages=[aiohttp.WSMessage(aiohttp.WSMsgType.CLOSED, None, None)])

    with caplog.at_level(logging.WARNING):
        await coordinator._ws_reader(ws)

    assert "Connection to GARDENA smart Gateway closed" in caplog.text


# ---------------------------------------------------------------------------
# _msg_consumer
# ---------------------------------------------------------------------------


async def test_msg_consumer_resolves_pending_reply_future(
    hass: HomeAssistant, coordinator: GardenaSmartLocalCoordinator
) -> None:
    coordinator._handle_messages = AsyncMock()
    loop = asyncio.get_running_loop()
    future = loop.create_future()
    coordinator._pending_replies["req-1"] = future

    reply = Reply(request_id="req-1", success=True)
    coordinator._msg_queue.put_nowait(IngressMessageList([reply]).model_dump_json())

    task = hass.async_create_task(coordinator._msg_consumer())
    await _pump()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert future.done()
    assert future.result().request_id == "req-1"
    coordinator._handle_messages.assert_not_awaited()


async def test_msg_consumer_forwards_non_reply_to_handle_messages(
    hass: HomeAssistant, coordinator: GardenaSmartLocalCoordinator
) -> None:
    coordinator._handle_messages = AsyncMock()
    event = _includable_event()
    coordinator._msg_queue.put_nowait(IngressMessageList([event]).model_dump_json())

    task = hass.async_create_task(coordinator._msg_consumer())
    await _pump()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    coordinator._handle_messages.assert_awaited_once()
    (forwarded,), _ = coordinator._handle_messages.call_args
    assert len(forwarded) == 1


async def test_msg_consumer_ignores_malformed_json(
    hass: HomeAssistant, coordinator: GardenaSmartLocalCoordinator
) -> None:
    coordinator._handle_messages = AsyncMock()
    coordinator._msg_queue.put_nowait("not valid json")
    event = _includable_event()
    coordinator._msg_queue.put_nowait(IngressMessageList([event]).model_dump_json())

    task = hass.async_create_task(coordinator._msg_consumer())
    await _pump()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    coordinator._handle_messages.assert_awaited_once()


async def test_msg_consumer_exception_logged_and_reraised(
    hass: HomeAssistant,
    coordinator: GardenaSmartLocalCoordinator,
    caplog: pytest.LogCaptureFixture,
) -> None:
    coordinator._handle_messages = AsyncMock(side_effect=RuntimeError("boom"))
    event = _includable_event()
    coordinator._msg_queue.put_nowait(IngressMessageList([event]).model_dump_json())

    task = hass.async_create_task(coordinator._msg_consumer())
    with caplog.at_level(logging.ERROR):
        with pytest.raises(RuntimeError):
            await task

    assert "Message consumer failed" in caplog.text


async def test_msg_consumer_cancelled_reraises(
    hass: HomeAssistant, coordinator: GardenaSmartLocalCoordinator
) -> None:
    task = hass.async_create_task(coordinator._msg_consumer())
    await _pump()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert task.cancelled()


# ---------------------------------------------------------------------------
# _do_discovery
# ---------------------------------------------------------------------------


def _device_map(**devices) -> DeviceMap:
    dm = DeviceMap({})
    for device_id, device in devices.items():
        dm[device_id] = device
    return dm


async def test_do_discovery_success_broadcasts_by_default(
    coordinator: GardenaSmartLocalCoordinator, mock_device
) -> None:
    coordinator.send_request = AsyncMock(return_value=IngressMessageList([]))
    device = mock_device(device_id="device-1")
    with patch.object(
        coordinator_module,
        "create_devices_from_messages",
        AsyncMock(return_value=_device_map(**{"device-1": device})),
    ):
        with patch.object(coordinator, "async_set_updated_data") as set_updated:
            await coordinator._do_discovery()

    coordinator.send_request.assert_awaited_once()
    call = coordinator.send_request.await_args
    assert call.args[0] == "discovery"
    assert call.kwargs == {"wait_for_response_sec": 30}
    assert coordinator._devices["device-1"] is device
    set_updated.assert_called_once_with(coordinator._devices)


async def test_do_discovery_broadcast_false_skips_set_updated_data(
    coordinator: GardenaSmartLocalCoordinator, mock_device
) -> None:
    coordinator.send_request = AsyncMock(return_value=IngressMessageList([]))
    device = mock_device(device_id="device-1")
    with patch.object(
        coordinator_module,
        "create_devices_from_messages",
        AsyncMock(return_value=_device_map(**{"device-1": device})),
    ):
        with patch.object(coordinator, "async_set_updated_data") as set_updated:
            await coordinator._do_discovery(broadcast=False)

    set_updated.assert_not_called()


async def test_do_discovery_timeout_raises_runtime_error(
    coordinator: GardenaSmartLocalCoordinator,
) -> None:
    coordinator.send_request = AsyncMock(side_effect=asyncio.TimeoutError())

    with pytest.raises(RuntimeError):
        await coordinator._do_discovery()


# ---------------------------------------------------------------------------
# _handle_messages
# ---------------------------------------------------------------------------


async def test_handle_messages_delete_event_drops_device(
    coordinator: GardenaSmartLocalCoordinator, mock_device
) -> None:
    device = mock_device(device_id="device-1")
    coordinator._devices["device-1"] = device
    coordinator.async_drop_device = MagicMock()

    event = Event(
        op="delete", entity=Entity(device="device-1", path=IpsoPath()), payload={}
    )
    await coordinator._handle_messages(IngressMessageList([event]))

    coordinator.async_drop_device.assert_called_once_with("device-1")


async def test_handle_messages_update_event_updates_device_and_batches_broadcast(
    coordinator: GardenaSmartLocalCoordinator, mock_device
) -> None:
    device_a = mock_device(device_id="device-a", is_online=True)
    device_b = mock_device(device_id="device-b", is_online=True)
    coordinator._devices["device-a"] = device_a
    coordinator._devices["device-b"] = device_b

    event_a = Event(
        op="update",
        entity=Entity(device="device-a", path=IpsoPath(object_name="sensor")),
        payload={"vb": True},
    )
    event_b = Event(
        op="update",
        entity=Entity(device="device-b", path=IpsoPath(object_name="sensor")),
        payload={"vb": True},
    )

    with patch.object(coordinator, "async_set_updated_data") as set_updated:
        await coordinator._handle_messages(IngressMessageList([event_a, event_b]))

    device_a.update_data.assert_called_once_with(event_a)
    device_b.update_data.assert_called_once_with(event_b)
    set_updated.assert_called_once_with(coordinator._devices)


async def test_handle_messages_logs_online_status_change(
    coordinator: GardenaSmartLocalCoordinator,
    mock_device,
    caplog: pytest.LogCaptureFixture,
) -> None:
    device = mock_device(device_id="device-1", is_online=True)

    def _go_offline(_event: Event) -> None:
        device.is_online = False

    device.update_data.side_effect = _go_offline
    coordinator._devices["device-1"] = device

    event = Event(
        op="update",
        entity=Entity(device="device-1", path=IpsoPath(object_name="sensor")),
        payload={},
    )
    with caplog.at_level(logging.INFO):
        await coordinator._handle_messages(IngressMessageList([event]))

    assert "connection status changed" in caplog.text


async def test_handle_messages_event_without_device_id_ignored(
    coordinator: GardenaSmartLocalCoordinator,
) -> None:
    event = Event(op="update", entity=Entity(path=IpsoPath()), payload={})
    with patch.object(coordinator, "async_set_updated_data") as set_updated:
        await coordinator._handle_messages(IngressMessageList([event]))
    set_updated.assert_not_called()


async def test_handle_messages_includable_event_routed(
    coordinator: GardenaSmartLocalCoordinator,
) -> None:
    coordinator._handle_includable_event = AsyncMock()
    event = _includable_event()
    await coordinator._handle_messages(IngressMessageList([event]))
    coordinator._handle_includable_event.assert_awaited_once_with(event)


async def test_handle_messages_exception_caught_and_logged(
    coordinator: GardenaSmartLocalCoordinator,
    mock_device,
    caplog: pytest.LogCaptureFixture,
) -> None:
    device = mock_device(device_id="device-1")
    device.update_data.side_effect = RuntimeError("boom")
    coordinator._devices["device-1"] = device

    event = Event(
        op="update",
        entity=Entity(device="device-1", path=IpsoPath(object_name="sensor")),
        payload={},
    )
    with caplog.at_level(logging.WARNING):
        await coordinator._handle_messages(IngressMessageList([event]))

    assert "Error handling messages" in caplog.text


# ---------------------------------------------------------------------------
# Includable device discovery
# ---------------------------------------------------------------------------


async def test_handle_includable_event_missing_instance_id_noop(
    coordinator: GardenaSmartLocalCoordinator,
) -> None:
    event = Event(
        op="update",
        entity=Entity(path=IpsoPath(object_name="includable_device")),
        payload={},
    )
    await coordinator._handle_includable_event(event)
    assert coordinator.includable_devices == {}


async def test_handle_includable_event_delete_removes_entry(
    coordinator: GardenaSmartLocalCoordinator,
) -> None:
    handle = MagicMock()
    coordinator._includable_timeouts["instance-1"] = handle
    coordinator._includable_devices["instance-1"] = IncludableDeviceInfo(
        instance_id="instance-1",
        service="svc",
        device_id="device-1",
        device_name="Device",
    )

    event = _includable_event(op="delete")
    await coordinator._handle_includable_event(event)

    handle.cancel.assert_called_once()
    assert coordinator.includable_devices == {}


async def test_handle_includable_event_new_device_discovered(
    hass: HomeAssistant, coordinator: GardenaSmartLocalCoordinator
) -> None:
    sgtin = MagicMock()
    sgtin.serial = 42
    sgtin.get_model_name = AsyncMock(return_value="Water Control")

    event = _includable_event(identifier="ABCDEF0123456789ABCDEF01")
    with patch.object(coordinator_module.SGTIN96Info, "from_hex", return_value=sgtin):
        await coordinator._handle_includable_event(event)

    assert "instance-1" in coordinator.includable_devices
    info = coordinator.includable_devices["instance-1"]
    assert info.device_id == "ABCDEF0123456789ABCDEF01"
    assert info.device_name == "Water Control 00000042"
    assert "instance-1" in coordinator._includable_timeouts

    coordinator._includable_timeouts.pop("instance-1").cancel()


async def test_handle_includable_event_heartbeat_reschedules_only(
    hass: HomeAssistant, coordinator: GardenaSmartLocalCoordinator
) -> None:
    coordinator._includable_devices["instance-1"] = IncludableDeviceInfo(
        instance_id="instance-1", service="svc", device_id="d1", device_name="Device"
    )
    old_handle = MagicMock()
    coordinator._includable_timeouts["instance-1"] = old_handle

    event = _includable_event()
    await coordinator._handle_includable_event(event)

    old_handle.cancel.assert_called_once()
    assert len(coordinator.includable_devices) == 1
    coordinator._includable_timeouts.pop("instance-1").cancel()


async def test_handle_includable_event_unparseable_identifier_ignored(
    coordinator: GardenaSmartLocalCoordinator,
) -> None:
    event = _includable_event(identifier="not-a-valid-sgtin")
    await coordinator._handle_includable_event(event)
    assert coordinator.includable_devices == {}


async def test_handle_includable_event_missing_service_ignored(
    coordinator: GardenaSmartLocalCoordinator,
) -> None:
    event = _includable_event(service=None)
    await coordinator._handle_includable_event(event)
    assert coordinator.includable_devices == {}


async def test_handle_includable_event_missing_identifier_ignored(
    coordinator: GardenaSmartLocalCoordinator,
) -> None:
    event = _includable_event(identifier=None)
    await coordinator._handle_includable_event(event)
    assert coordinator.includable_devices == {}


def test_expire_includable_removes_entry(
    coordinator: GardenaSmartLocalCoordinator,
) -> None:
    coordinator._includable_devices["instance-1"] = IncludableDeviceInfo(
        instance_id="instance-1", service="svc", device_id="d1", device_name="Device"
    )
    coordinator._includable_timeouts["instance-1"] = MagicMock()

    coordinator._expire_includable("instance-1")

    assert coordinator.includable_devices == {}
    assert coordinator._includable_timeouts == {}


# ---------------------------------------------------------------------------
# async_include_device
# ---------------------------------------------------------------------------


async def test_async_include_device_unknown_instance_returns_none(
    coordinator: GardenaSmartLocalCoordinator,
) -> None:
    assert await coordinator.async_include_device("unknown") is None


async def test_async_include_device_send_request_timeout_returns_none(
    coordinator: GardenaSmartLocalCoordinator,
) -> None:
    coordinator._includable_devices["instance-1"] = IncludableDeviceInfo(
        instance_id="instance-1", service="svc", device_id="d1", device_name="Device"
    )
    coordinator.send_request = AsyncMock(side_effect=asyncio.TimeoutError())

    assert await coordinator.async_include_device("instance-1") is None


async def test_async_include_device_send_request_error_returns_none(
    coordinator: GardenaSmartLocalCoordinator,
) -> None:
    coordinator._includable_devices["instance-1"] = IncludableDeviceInfo(
        instance_id="instance-1", service="svc", device_id="d1", device_name="Device"
    )
    coordinator.send_request = AsyncMock(side_effect=RuntimeError("boom"))

    assert await coordinator.async_include_device("instance-1") is None


async def test_async_include_device_no_successful_reply_returns_none(
    coordinator: GardenaSmartLocalCoordinator,
) -> None:
    coordinator._includable_devices["instance-1"] = IncludableDeviceInfo(
        instance_id="instance-1", service="svc", device_id="d1", device_name="Device"
    )
    coordinator.send_request = AsyncMock(
        return_value=IngressMessageList([Reply(request_id="instance-1", success=False)])
    )

    assert await coordinator.async_include_device("instance-1") is None


async def test_async_include_device_completion_timeout_returns_none(
    coordinator: GardenaSmartLocalCoordinator, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(coordinator_module, "INCLUSION_TIMEOUT", 2)
    coordinator._includable_devices["instance-1"] = IncludableDeviceInfo(
        instance_id="instance-1", service="svc", device_id="d1", device_name="Device"
    )
    coordinator.send_request = AsyncMock(
        return_value=IngressMessageList([Reply(request_id="instance-1", success=True)])
    )

    with patch.object(coordinator_module.asyncio, "sleep", AsyncMock()):
        result = await coordinator.async_include_device("instance-1")

    assert result is None
    assert "instance-1" in coordinator._includable_devices


def _pop_includable_on_sleep(
    coordinator: GardenaSmartLocalCoordinator, instance_id: str
):
    """asyncio.sleep replacement that removes the includable device on first call."""

    async def fake_sleep(_delay: float) -> None:
        coordinator._includable_devices.pop(instance_id, None)

    return fake_sleep


async def test_async_include_device_rediscovery_failure_returns_none(
    coordinator: GardenaSmartLocalCoordinator,
) -> None:
    coordinator._includable_devices["instance-1"] = IncludableDeviceInfo(
        instance_id="instance-1", service="svc", device_id="d1", device_name="Device"
    )
    coordinator.send_request = AsyncMock(
        return_value=IngressMessageList([Reply(request_id="instance-1", success=True)])
    )
    coordinator._do_discovery = AsyncMock(side_effect=RuntimeError("boom"))

    with patch.object(
        coordinator_module.asyncio,
        "sleep",
        _pop_includable_on_sleep(coordinator, "instance-1"),
    ):
        assert await coordinator.async_include_device("instance-1") is None


async def test_async_include_device_missing_after_discovery_returns_none(
    coordinator: GardenaSmartLocalCoordinator,
) -> None:
    coordinator._includable_devices["instance-1"] = IncludableDeviceInfo(
        instance_id="instance-1", service="svc", device_id="d1", device_name="Device"
    )
    coordinator.send_request = AsyncMock(
        return_value=IngressMessageList([Reply(request_id="instance-1", success=True)])
    )
    coordinator._do_discovery = AsyncMock()

    with patch.object(
        coordinator_module.asyncio,
        "sleep",
        _pop_includable_on_sleep(coordinator, "instance-1"),
    ):
        assert await coordinator.async_include_device("instance-1") is None
    coordinator._do_discovery.assert_awaited_once_with(broadcast=False)


async def test_async_include_device_success(
    coordinator: GardenaSmartLocalCoordinator, mock_device
) -> None:
    coordinator._includable_devices["instance-1"] = IncludableDeviceInfo(
        instance_id="instance-1",
        service="svc",
        device_id="device-1",
        device_name="Device",
    )
    coordinator.send_request = AsyncMock(
        return_value=IngressMessageList([Reply(request_id="instance-1", success=True)])
    )

    async def fake_discovery(broadcast: bool = True) -> None:
        coordinator._devices["device-1"] = mock_device(device_id="device-1")

    coordinator._do_discovery = fake_discovery

    with patch.object(
        coordinator_module.asyncio,
        "sleep",
        _pop_includable_on_sleep(coordinator, "instance-1"),
    ):
        result = await coordinator.async_include_device("instance-1")
    assert result == "device-1"


# ---------------------------------------------------------------------------
# async_drop_device / async_exclude_device
# ---------------------------------------------------------------------------


def test_async_drop_device_removes_and_broadcasts(
    coordinator: GardenaSmartLocalCoordinator, mock_device
) -> None:
    coordinator._devices["device-1"] = mock_device(device_id="device-1")
    with patch.object(coordinator, "async_set_updated_data") as set_updated:
        coordinator.async_drop_device("device-1")
    set_updated.assert_called_once_with(coordinator._devices)
    assert "device-1" not in coordinator._devices


def test_async_drop_device_unknown_is_noop(
    coordinator: GardenaSmartLocalCoordinator,
) -> None:
    with patch.object(coordinator, "async_set_updated_data") as set_updated:
        coordinator.async_drop_device("unknown")
    set_updated.assert_not_called()


async def test_async_exclude_device_unknown_returns_false(
    coordinator: GardenaSmartLocalCoordinator,
) -> None:
    assert await coordinator.async_exclude_device("unknown") is False


async def test_async_exclude_device_success_drops_before_request(
    coordinator: GardenaSmartLocalCoordinator, mock_device
) -> None:
    device = mock_device(device_id="device-1")
    coordinator._devices["device-1"] = device
    coordinator.send_request = AsyncMock(
        return_value=IngressMessageList([Reply(request_id="req-1", success=True)])
    )

    result = await coordinator.async_exclude_device("device-1")

    assert result is True
    assert "device-1" not in coordinator._devices
    device.build_exclusion_obj.assert_called_once()


async def test_async_exclude_device_timeout_returns_false(
    coordinator: GardenaSmartLocalCoordinator, mock_device
) -> None:
    coordinator._devices["device-1"] = mock_device(device_id="device-1")
    coordinator.send_request = AsyncMock(side_effect=asyncio.TimeoutError())

    assert await coordinator.async_exclude_device("device-1") is False


async def test_async_exclude_device_error_returns_false(
    coordinator: GardenaSmartLocalCoordinator, mock_device
) -> None:
    coordinator._devices["device-1"] = mock_device(device_id="device-1")
    coordinator.send_request = AsyncMock(side_effect=RuntimeError("boom"))

    assert await coordinator.async_exclude_device("device-1") is False


async def test_async_exclude_device_no_success_reply_returns_false(
    coordinator: GardenaSmartLocalCoordinator, mock_device
) -> None:
    coordinator._devices["device-1"] = mock_device(device_id="device-1")
    coordinator.send_request = AsyncMock(
        return_value=IngressMessageList([Reply(request_id="req-1", success=False)])
    )

    assert await coordinator.async_exclude_device("device-1") is False


# ---------------------------------------------------------------------------
# _update_device / _update_devices
# ---------------------------------------------------------------------------


def test_update_device_adds_new_device(
    coordinator: GardenaSmartLocalCoordinator, mock_device
) -> None:
    device = mock_device(device_id="device-1")
    coordinator._update_device(device)
    assert coordinator._devices["device-1"] is device


def test_update_device_updates_existing_device(
    coordinator: GardenaSmartLocalCoordinator, mock_device
) -> None:
    old = mock_device(device_id="device-1")
    new = mock_device(device_id="device-1")
    coordinator._devices["device-1"] = old
    coordinator._update_device(new)
    assert coordinator._devices["device-1"] is new


def test_update_devices_handles_exception(
    coordinator: GardenaSmartLocalCoordinator,
    caplog: pytest.LogCaptureFixture,
) -> None:
    bad_devices = MagicMock()
    bad_devices.values.side_effect = RuntimeError("boom")

    with caplog.at_level(logging.WARNING):
        coordinator._update_devices(bad_devices)

    assert "Failed to update devices" in caplog.text


# ---------------------------------------------------------------------------
# send_request
# ---------------------------------------------------------------------------


async def test_send_request_without_ws_returns_empty(
    coordinator: GardenaSmartLocalCoordinator,
) -> None:
    from gardena_smart_local_api.devices import build_discovery_obj

    coordinator._ws = None
    result = await coordinator.send_request("device-1", build_discovery_obj())
    assert list(result) == []


async def test_send_request_with_closed_ws_returns_empty(
    coordinator: GardenaSmartLocalCoordinator, fake_ws
) -> None:
    from gardena_smart_local_api.devices import build_discovery_obj

    ws = fake_ws()
    ws.closed = True
    coordinator._ws = ws
    result = await coordinator.send_request("device-1", build_discovery_obj())
    assert list(result) == []
    assert ws.sent == []


async def test_send_request_fire_and_forget(
    coordinator: GardenaSmartLocalCoordinator, fake_ws
) -> None:
    from gardena_smart_local_api.devices import build_discovery_obj

    ws = fake_ws()
    coordinator._ws = ws
    result = await coordinator.send_request("device-1", build_discovery_obj())
    assert list(result) == []
    assert len(ws.sent) == 1
    assert coordinator._pending_replies == {}


async def test_send_request_waits_for_reply(
    hass: HomeAssistant, coordinator: GardenaSmartLocalCoordinator, fake_ws
) -> None:
    from gardena_smart_local_api.messages import Request

    ws = fake_ws()
    coordinator._ws = ws
    request = Request(op="read", entity=Entity(path=IpsoPath()), request_id="req-1")

    async def resolve_soon() -> None:
        await asyncio.sleep(0)
        future = coordinator._pending_replies["req-1"]
        future.set_result(Reply(request_id="req-1", success=True))

    hass.async_create_task(resolve_soon())
    from gardena_smart_local_api.messages import EgressMessageList

    replies = await coordinator.send_request(
        "device-1", EgressMessageList([request]), wait_for_response_sec=5
    )
    assert len(list(replies)) == 1
    assert list(replies)[0].request_id == "req-1"


async def test_send_request_timeout_purges_pending(
    coordinator: GardenaSmartLocalCoordinator, fake_ws
) -> None:
    from gardena_smart_local_api.messages import EgressMessageList, Request

    ws = fake_ws()
    coordinator._ws = ws
    request = Request(op="read", entity=Entity(path=IpsoPath()), request_id="req-1")

    with pytest.raises(asyncio.TimeoutError):
        await coordinator.send_request(
            "device-1", EgressMessageList([request]), wait_for_response_sec=0.01
        )

    assert coordinator._pending_replies == {}
