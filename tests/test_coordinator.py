# SPDX-FileCopyrightText: 2026 GARDENA GmbH
#
# SPDX-License-Identifier: Apache-2.0

"""Tests for the GARDENA smart local coordinator."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

import pytest
from gardena_smart_local_api.client import DiscoveryError, GatewayClient, RequestError
from gardena_smart_local_api.devices import DeviceMap
from gardena_smart_local_api.messages import IngressMessageList
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.gardena_smart_local_preview.const import DOMAIN
from custom_components.gardena_smart_local_preview.coordinator import (
    GardenaSmartLocalCoordinator,
    IncludableDeviceInfo,
)


@pytest.fixture
async def coordinator(hass: HomeAssistant) -> GardenaSmartLocalCoordinator:
    """Return a coordinator that is not connected to a gateway."""
    entry = MockConfigEntry(domain=DOMAIN)
    entry.add_to_hass(hass)
    return GardenaSmartLocalCoordinator(
        hass, entry, "192.168.1.100", 8443, "testpassword"
    )


def test_schedule_unknown_device_discovery_collapses_burst(
    coordinator: GardenaSmartLocalCoordinator,
) -> None:
    """A burst of events collapses into a single pending re-discovery."""
    handle = MagicMock()
    coordinator.hass.loop.call_later = MagicMock(return_value=handle)

    coordinator._schedule_unknown_device_discovery("dev-1")
    coordinator._schedule_unknown_device_discovery("dev-2")

    coordinator.hass.loop.call_later.assert_called_once()
    handle.cancel.assert_not_called()
    assert coordinator._unknown_device_discovery_handle is handle


async def test_discover_unknown_devices_runs_full_discovery(
    coordinator: GardenaSmartLocalCoordinator,
) -> None:
    """The debounced run re-discovers and clears its handle.

    The handle here stands for "a run is scheduled" (see
    _schedule_unknown_device_discovery). By the time this runs, the real
    timer has already elapsed, so the handle is just a stale reference to
    clear, not something to cancel; a MagicMock stands in for it.
    """
    coordinator._unknown_device_discovery_handle = MagicMock()
    coordinator._do_discovery = AsyncMock()

    await coordinator._discover_unknown_devices()

    coordinator._do_discovery.assert_awaited_once()
    assert coordinator._unknown_device_discovery_handle is None


async def test_discover_unknown_devices_failure_clears_handle(
    coordinator: GardenaSmartLocalCoordinator,
) -> None:
    """A failed re-discovery still clears the handle, so a later event can retry."""
    coordinator._unknown_device_discovery_handle = MagicMock()
    coordinator._do_discovery = AsyncMock(side_effect=RuntimeError("boom"))

    await coordinator._discover_unknown_devices()

    assert coordinator._unknown_device_discovery_handle is None


async def test_async_disconnect_cancels_pending_rediscovery(
    coordinator: GardenaSmartLocalCoordinator,
) -> None:
    """Disconnecting cancels a still-pending re-discovery timer."""
    handle = coordinator.hass.loop.call_later(99, lambda: None)
    coordinator._unknown_device_discovery_handle = handle

    await coordinator.async_disconnect()

    assert coordinator._unknown_device_discovery_handle is None


def test_update_devices_survives_a_broken_device(
    coordinator: GardenaSmartLocalCoordinator,
) -> None:
    """A device that cannot be applied does not block the devices after it."""
    broken, healthy = MagicMock(id="broken"), MagicMock(id="healthy")
    original = coordinator._update_device

    def _update(device: MagicMock) -> None:
        if device is broken:
            raise RuntimeError("bad")
        original(device)

    with patch.object(coordinator, "_update_device", side_effect=_update):
        coordinator._update_devices({"broken": broken, "healthy": healthy})

    assert list(coordinator._devices.keys()) == ["healthy"]


async def test_client_is_set_up_for_the_gateway(hass: HomeAssistant) -> None:
    """The client reports back to the coordinator."""
    entry = MockConfigEntry(domain=DOMAIN)
    entry.add_to_hass(hass)

    with patch(
        "custom_components.gardena_smart_local_preview.coordinator.GatewayClient"
    ) as client_class:
        coordinator = GardenaSmartLocalCoordinator(
            hass, entry, "192.168.1.100", 8443, "testpassword"
        )

    client_class.assert_called_once_with(
        "192.168.1.100",
        8443,
        "testpassword",
        session=async_get_clientsession(hass),
        on_connect=coordinator._async_on_connect,
        on_event=coordinator._async_on_event,
        on_disconnect=coordinator._on_disconnect,
        on_auth_failed=coordinator._on_auth_failed,
    )
    assert coordinator.client is client_class.return_value


async def test_rejected_password_starts_reauthentication(
    coordinator: GardenaSmartLocalCoordinator,
) -> None:
    """Once the client gives up on the password, the user is asked for a new one."""
    with patch.object(coordinator.config_entry, "async_start_reauth") as start_reauth:
        coordinator._on_auth_failed()

    start_reauth.assert_called_once_with(coordinator.hass)


async def test_uri_and_connected_come_from_the_client(
    coordinator: GardenaSmartLocalCoordinator,
) -> None:
    """The coordinator reports what the client knows about the connection."""
    assert coordinator.uri == "wss://192.168.1.100:8443"

    for connected in (True, False):
        with patch.object(
            GatewayClient, "connected", new_callable=PropertyMock
        ) as client_connected:
            client_connected.return_value = connected
            assert coordinator.connected is connected


async def test_connect_and_disconnect_use_the_client(
    coordinator: GardenaSmartLocalCoordinator,
) -> None:
    """Connecting and disconnecting is left to the client."""
    with (
        patch.object(coordinator.client, "connect", AsyncMock()) as connect,
        patch.object(coordinator.client, "disconnect", AsyncMock()) as disconnect,
    ):
        await coordinator.async_connect()
        await coordinator.async_disconnect()

    connect.assert_awaited_once_with()
    disconnect.assert_awaited_once_with()


async def test_every_connect_runs_discovery(
    coordinator: GardenaSmartLocalCoordinator,
) -> None:
    """The client hands over each (re)connect, and the devices are discovered."""
    device = MagicMock(id="dev-1")
    discover = AsyncMock(return_value={"dev-1": device})

    with patch.object(coordinator.client, "discover_devices", discover):
        await coordinator._async_on_connect()

    discover.assert_awaited_once()
    assert dict(coordinator.data.items()) == {"dev-1": device}


async def test_failed_discovery_keeps_the_known_devices(
    coordinator: GardenaSmartLocalCoordinator,
) -> None:
    """A discovery the gateway answered with an error is not applied."""
    known = MagicMock(id="dev-1")
    coordinator._devices = {"dev-1": known}
    error = DiscoveryError("failed", IngressMessageList([]), DeviceMap({}))

    with (
        patch.object(
            coordinator.client, "discover_devices", AsyncMock(side_effect=error)
        ),
        pytest.raises(DiscoveryError),
    ):
        await coordinator._async_on_connect()

    assert coordinator._devices == {"dev-1": known}


async def test_lost_connection_updates_the_entities(
    coordinator: GardenaSmartLocalCoordinator,
) -> None:
    """Entities re-check their availability when the connection drops."""
    with patch.object(coordinator, "async_update_listeners") as update_listeners:
        coordinator._on_disconnect()

    update_listeners.assert_called_once_with()


async def test_event_that_updated_a_device_is_published(
    coordinator: GardenaSmartLocalCoordinator,
) -> None:
    """An event that changed a device publishes the device map."""
    with (
        patch.object(coordinator, "_handle_event", AsyncMock(return_value="dev-1")),
        patch.object(coordinator, "async_set_updated_data") as updated,
    ):
        await coordinator._async_on_event(MagicMock())

    updated.assert_called_once_with(coordinator._devices)


async def test_event_that_changed_nothing_is_not_published(
    coordinator: GardenaSmartLocalCoordinator,
) -> None:
    """An event that updated no device publishes nothing."""
    with (
        patch.object(coordinator, "_handle_event", AsyncMock(return_value=None)),
        patch.object(coordinator, "async_set_updated_data") as updated,
    ):
        await coordinator._async_on_event(MagicMock())

    updated.assert_not_called()


async def test_event_for_a_device_with_a_command_in_flight_is_held_back(
    coordinator: GardenaSmartLocalCoordinator,
) -> None:
    """The intermediate states of a command are not shown while it is running."""
    coordinator._pending_reply_devices["dev-1"] = 1

    with (
        patch.object(coordinator, "_handle_event", AsyncMock(return_value="dev-1")),
        patch.object(coordinator, "async_set_updated_data") as updated,
    ):
        await coordinator._async_on_event(MagicMock())

    updated.assert_not_called()


async def test_failing_event_is_logged_and_skipped(
    coordinator: GardenaSmartLocalCoordinator, caplog: pytest.LogCaptureFixture
) -> None:
    """One bad event must not stop the events after it."""
    with (
        patch.object(
            coordinator, "_handle_event", AsyncMock(side_effect=RuntimeError("bad"))
        ),
        patch.object(coordinator, "async_set_updated_data") as updated,
    ):
        await coordinator._async_on_event(MagicMock())

    assert "Error handling event" in caplog.text
    updated.assert_not_called()


async def test_waiting_request_holds_back_events_until_it_settles(
    coordinator: GardenaSmartLocalCoordinator,
) -> None:
    """A device is marked while a command runs, and its state is published after."""
    seen_while_waiting: list[bool] = []

    async def _send(request: object, timeout: float | None) -> IngressMessageList:
        seen_while_waiting.append("dev-1" in coordinator._pending_reply_devices)
        return IngressMessageList([])

    with (
        patch.object(coordinator.client, "send_request", _send),
        patch.object(coordinator, "async_set_updated_data") as updated,
    ):
        await coordinator.send_request("dev-1", MagicMock(), wait_for_response_sec=5)

    assert seen_while_waiting == [True]
    assert not coordinator._pending_reply_devices
    updated.assert_called_once_with(coordinator._devices)


async def test_rejected_request_still_publishes_and_raises(
    coordinator: GardenaSmartLocalCoordinator,
) -> None:
    """A command the gateway rejects settles too, and the caller sees the error."""
    error = RequestError("rejected", IngressMessageList([]))

    with (
        patch.object(coordinator.client, "send_request", AsyncMock(side_effect=error)),
        patch.object(coordinator, "async_set_updated_data") as updated,
        pytest.raises(RequestError),
    ):
        await coordinator.send_request("dev-1", MagicMock(), wait_for_response_sec=5)

    assert not coordinator._pending_reply_devices
    updated.assert_called_once_with(coordinator._devices)


async def test_request_without_wait_is_only_sent(
    coordinator: GardenaSmartLocalCoordinator,
) -> None:
    """Without a wait nothing is tracked, published or returned."""
    send = AsyncMock()
    request = MagicMock()

    with (
        patch.object(coordinator.client, "send_request", send),
        patch.object(coordinator, "async_set_updated_data") as updated,
    ):
        replies = await coordinator.send_request("dev-1", request)

    send.assert_awaited_once_with(request, timeout=None)
    assert list(replies) == []
    updated.assert_not_called()


def _excludable_device() -> MagicMock:
    device = MagicMock()
    device.id = "dev-1"
    device.build_exclusion_obj.return_value = "EXCLUDE_OBJ"
    return device


async def test_exclude_success_drops_the_device(
    coordinator: GardenaSmartLocalCoordinator,
) -> None:
    """A confirmed exclusion removes the device."""
    device = _excludable_device()
    coordinator._devices = {device.id: device}

    with patch.object(coordinator.client, "send_request", AsyncMock()):
        assert await coordinator.async_exclude_device(device.id) is True

    assert device.id not in coordinator._devices


@pytest.mark.parametrize(
    "outcome",
    [
        TimeoutError(),
        ConnectionError("not connected"),
        RequestError("rejected", IngressMessageList([])),
        RuntimeError("boom"),
    ],
)
async def test_exclude_failure_reports_false(
    coordinator: GardenaSmartLocalCoordinator, outcome: Exception
) -> None:
    """An exclusion the gateway does not confirm is reported as failed."""
    device = _excludable_device()
    coordinator._devices = {device.id: device}

    with patch.object(
        coordinator.client, "send_request", AsyncMock(side_effect=outcome)
    ):
        assert await coordinator.async_exclude_device(device.id) is False


@pytest.mark.parametrize(
    "outcome",
    [
        TimeoutError(),
        ConnectionError("not connected"),
        RequestError("rejected", IngressMessageList([])),
        RuntimeError("boom"),
    ],
)
async def test_include_fails_when_the_request_fails(
    coordinator: GardenaSmartLocalCoordinator, outcome: Exception
) -> None:
    """An inclusion request that fails reports no device."""
    coordinator._includable_devices["inst-1"] = IncludableDeviceInfo(
        "inst-1", "svc", "dev-1", "Valve"
    )

    with (
        patch(
            "custom_components.gardena_smart_local_preview.coordinator.build_inclusion_obj"
        ),
        patch.object(
            coordinator.client, "send_request", AsyncMock(side_effect=outcome)
        ),
    ):
        assert await coordinator.async_include_device("inst-1") is None

    assert not coordinator._including_device_ids
