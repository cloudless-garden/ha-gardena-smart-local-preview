# SPDX-FileCopyrightText: 2026 GARDENA GmbH
#
# SPDX-License-Identifier: Apache-2.0

"""Tests for the GARDENA smart local lawn mower platform."""

from __future__ import annotations

from unittest.mock import MagicMock

from custom_components.gardena_smart_local_preview.const import (
    CONF_MOWER_DURATION,
    DEFAULT_MOWER_DURATION_HOURS,
)
from custom_components.gardena_smart_local_preview.lawn_mower import GardenaMower


async def test_start_mowing_uses_default_duration(
    coordinator: MagicMock, entry: MagicMock, mock_device: MagicMock
) -> None:
    """Starting without a configured duration falls back to the default."""
    mower = GardenaMower(coordinator, entry, mock_device)

    await mower.async_start_mowing()

    mock_device.build_start_mowing_obj.assert_called_once_with(
        DEFAULT_MOWER_DURATION_HOURS * 3600
    )
    coordinator.send_request.assert_awaited_once()


async def test_start_mowing_uses_configured_duration(
    coordinator: MagicMock,
    entry: MagicMock,
    mock_device: MagicMock,
    subentry: MagicMock,
) -> None:
    """A duration stored in the device subentry is used for the start command."""
    subentry.data[CONF_MOWER_DURATION] = 2
    mower = GardenaMower(coordinator, entry, mock_device)

    await mower.async_start_mowing()

    mock_device.build_start_mowing_obj.assert_called_once_with(7200)


async def test_dock_stops_mowing(
    coordinator: MagicMock, entry: MagicMock, mock_device: MagicMock
) -> None:
    """Docking builds the stop command."""
    mower = GardenaMower(coordinator, entry, mock_device)

    await mower.async_dock()

    mock_device.build_stop_mowing_obj.assert_called_once_with()
