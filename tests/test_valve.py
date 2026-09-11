# SPDX-FileCopyrightText: 2026 GARDENA GmbH
#
# SPDX-License-Identifier: Apache-2.0

"""Tests for the GARDENA smart local valve platform."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from gardena_smart_local_api.messages import Reply
from homeassistant.exceptions import HomeAssistantError

from custom_components.gardena_smart_local_preview.const import (
    DEFAULT_VALVE_DURATION_MINUTES,
)
from custom_components.gardena_smart_local_preview.valve import GardenaValve


@pytest.fixture
def mock_device(mock_device: MagicMock) -> MagicMock:
    """Return a device with a single, closed valve."""
    mock_device.valve_ids = [0]
    mock_device.is_valve_open.return_value = False
    return mock_device


def test_is_closed_inverts_is_valve_open(
    coordinator: MagicMock, entry: MagicMock, mock_device: MagicMock
) -> None:
    """is_closed is the inverse of the device's is_valve_open."""
    mock_device.is_valve_open.return_value = True
    valve = GardenaValve(coordinator, entry, mock_device, 0)

    assert valve.is_closed is False

    mock_device.is_valve_open.return_value = False
    assert valve.is_closed is True

    mock_device.is_valve_open.return_value = None
    assert valve.is_closed is None


def test_is_closed_none_when_device_unknown(
    coordinator: MagicMock, entry: MagicMock, mock_device: MagicMock
) -> None:
    """is_closed is None while the device is not in the coordinator data."""
    coordinator.data = {}
    valve = GardenaValve(coordinator, entry, mock_device, 0)

    assert valve.is_closed is None


def test_naming(
    coordinator: MagicMock, entry: MagicMock, mock_device: MagicMock
) -> None:
    """A single-valve device has no name; a multi-valve device is numbered."""
    single = GardenaValve(coordinator, entry, mock_device, 0)
    assert single.name is None
    assert single.unique_id == "dev-1_valve_0"

    mock_device.valve_ids = [0, 1]
    second = GardenaValve(coordinator, entry, mock_device, 1)
    assert second.translation_key == "valve"
    assert second.translation_placeholders == {"number": "2"}


async def test_open_valve_uses_default_duration(
    coordinator: MagicMock, entry: MagicMock, mock_device: MagicMock
) -> None:
    """Opening without a duration falls back to the configured default."""
    valve = GardenaValve(coordinator, entry, mock_device, 0)

    await valve.async_open_valve()

    mock_device.build_open_valve_obj.assert_called_once_with(
        0, DEFAULT_VALVE_DURATION_MINUTES * 60
    )
    coordinator.send_request.assert_awaited_once()


async def test_open_valve_for_custom_duration(
    coordinator: MagicMock, entry: MagicMock, mock_device: MagicMock
) -> None:
    """open_valve passes the requested duration straight through."""
    mock_device.valve_ids = [0, 1]
    valve = GardenaValve(coordinator, entry, mock_device, 1)

    await valve.async_open_valve_for(600)

    mock_device.build_open_valve_obj.assert_called_once_with(1, 600)


async def test_close_valve(
    coordinator: MagicMock, entry: MagicMock, mock_device: MagicMock
) -> None:
    """Closing builds the close command for the valve."""
    valve = GardenaValve(coordinator, entry, mock_device, 0)

    await valve.async_close_valve()

    mock_device.build_close_valve_obj.assert_called_once_with(0)


async def test_rejected_command_raises(
    coordinator: MagicMock, entry: MagicMock, mock_device: MagicMock
) -> None:
    """A negative reply from the gateway surfaces as an error."""
    coordinator.send_request = AsyncMock(
        return_value=[Reply(request_id="1", success=False)]
    )
    valve = GardenaValve(coordinator, entry, mock_device, 0)

    with pytest.raises(HomeAssistantError):
        await valve.async_close_valve()
