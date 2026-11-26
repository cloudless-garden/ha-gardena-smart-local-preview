# SPDX-FileCopyrightText: 2026 GARDENA GmbH
#
# SPDX-License-Identifier: Apache-2.0

"""Tests for the GARDENA smart local coordinator."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

import pytest
from gardena_smart_local_api.client import (
    DeviceManager,
    InclusionError,
    RequestError,
)
from gardena_smart_local_api.messages import IngressMessageList
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.gardena_smart_local_preview.const import DOMAIN
from custom_components.gardena_smart_local_preview.coordinator import (
    GardenaSmartLocalCoordinator,
)


@pytest.fixture
async def coordinator(hass: HomeAssistant) -> GardenaSmartLocalCoordinator:
    """Return a coordinator that is not connected to a gateway."""
    entry = MockConfigEntry(domain=DOMAIN)
    entry.add_to_hass(hass)
    return GardenaSmartLocalCoordinator(
        hass, entry, "192.168.1.100", 8443, "testpassword"
    )


async def test_manager_is_set_up_for_the_gateway(hass: HomeAssistant) -> None:
    """The manager reports back to the coordinator."""
    entry = MockConfigEntry(domain=DOMAIN)
    entry.add_to_hass(hass)

    with patch(
        "custom_components.gardena_smart_local_preview.coordinator.DeviceManager"
    ) as manager_class:
        coordinator = GardenaSmartLocalCoordinator(
            hass, entry, "192.168.1.100", 8443, "testpassword"
        )

    manager_class.assert_called_once_with(
        "192.168.1.100",
        8443,
        "testpassword",
        session=async_get_clientsession(hass),
        on_devices_changed=coordinator._on_devices_changed,
        on_disconnect=coordinator._on_disconnect,
        on_auth_failed=coordinator._on_auth_failed,
    )
    assert coordinator.manager is manager_class.return_value


async def test_rejected_password_starts_reauthentication(
    coordinator: GardenaSmartLocalCoordinator,
) -> None:
    """Once the manager gives up on the password, the user is asked for a new one."""
    with patch.object(coordinator.config_entry, "async_start_reauth") as start_reauth:
        coordinator._on_auth_failed()

    start_reauth.assert_called_once_with(coordinator.hass)


async def test_uri_and_connected_come_from_the_manager(
    coordinator: GardenaSmartLocalCoordinator,
) -> None:
    """The coordinator reports what the manager knows about the connection."""
    assert coordinator.uri == "wss://192.168.1.100:8443"

    for connected in (True, False):
        with patch.object(
            DeviceManager, "connected", new_callable=PropertyMock
        ) as manager_connected:
            manager_connected.return_value = connected
            assert coordinator.connected is connected


async def test_connect_and_disconnect_use_the_manager(
    coordinator: GardenaSmartLocalCoordinator,
) -> None:
    """Connecting and disconnecting is left to the manager."""
    with (
        patch.object(coordinator.manager, "connect", AsyncMock()) as connect,
        patch.object(coordinator.manager, "disconnect", AsyncMock()) as disconnect,
    ):
        await coordinator.async_connect()
        await coordinator.async_disconnect()

    connect.assert_awaited_once_with()
    disconnect.assert_awaited_once_with()


async def test_changed_devices_are_published(
    coordinator: GardenaSmartLocalCoordinator,
) -> None:
    """The entities get the devices of the manager when some of them changed."""
    device = MagicMock(id="dev-1")
    coordinator.manager._devices = {"dev-1": device}

    coordinator._on_devices_changed(frozenset({"dev-1"}))

    assert coordinator.data == {"dev-1": device}


async def test_lost_connection_updates_the_entities(
    coordinator: GardenaSmartLocalCoordinator,
) -> None:
    """Entities re-check their availability when the connection drops."""
    with patch.object(coordinator, "async_update_listeners") as update_listeners:
        coordinator._on_disconnect()

    update_listeners.assert_called_once_with()


async def test_include_returns_the_id_of_the_included_device(
    coordinator: GardenaSmartLocalCoordinator,
) -> None:
    """The caller publishes the new device itself, so the manager stays quiet."""
    include = AsyncMock(return_value=MagicMock(id="dev-1"))

    with patch.object(coordinator.manager, "include_device", include):
        device_id = await coordinator.async_include_device("instance-1")

    assert device_id == "dev-1"
    include.assert_awaited_once_with("instance-1", notify=False)


async def test_failed_inclusion_reports_none(
    coordinator: GardenaSmartLocalCoordinator,
) -> None:
    """The config flow gets None instead of the error."""
    include = AsyncMock(side_effect=InclusionError("not accepted"))

    with patch.object(coordinator.manager, "include_device", include):
        assert await coordinator.async_include_device("instance-1") is None


async def test_exclude_success(coordinator: GardenaSmartLocalCoordinator) -> None:
    """A device that the gateway excluded is reported as excluded."""
    exclude = AsyncMock()

    with patch.object(coordinator.manager, "exclude_device", exclude):
        assert await coordinator.async_exclude_device("dev-1") is True

    exclude.assert_awaited_once_with("dev-1")


@pytest.mark.parametrize(
    "error",
    [
        RequestError("rejected", IngressMessageList([])),
        TimeoutError(),
        ConnectionError(),
    ],
)
async def test_exclude_failure_reports_false(
    coordinator: GardenaSmartLocalCoordinator, error: Exception
) -> None:
    """The caller learns that the device is still paired with the gateway."""
    with patch.object(
        coordinator.manager, "exclude_device", AsyncMock(side_effect=error)
    ):
        assert await coordinator.async_exclude_device("dev-1") is False


async def test_refresh_firmware_uses_the_manager(
    coordinator: GardenaSmartLocalCoordinator,
) -> None:
    refresh = AsyncMock()

    with patch.object(coordinator.manager, "refresh_firmware", refresh):
        await coordinator.async_refresh_firmware("dev-1")

    refresh.assert_awaited_once_with("dev-1")


@pytest.mark.parametrize(
    "error",
    [
        RequestError("rejected", IngressMessageList([])),
        TimeoutError(),
        ConnectionError(),
    ],
)
async def test_refresh_firmware_failure_is_not_raised(
    coordinator: GardenaSmartLocalCoordinator, error: Exception
) -> None:
    """The refresh is best effort and must not disturb the entity."""
    with patch.object(
        coordinator.manager, "refresh_firmware", AsyncMock(side_effect=error)
    ):
        await coordinator.async_refresh_firmware("dev-1")


async def test_send_command_uses_the_manager(
    coordinator: GardenaSmartLocalCoordinator,
) -> None:
    replies = IngressMessageList([])
    send = AsyncMock(return_value=replies)
    request = MagicMock()

    with patch.object(coordinator.manager, "send_command", send):
        result = await coordinator.send_command("dev-1", request, 5)

    assert result is replies
    send.assert_awaited_once_with("dev-1", request, 5)
