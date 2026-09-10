# SPDX-FileCopyrightText: 2026 GARDENA GmbH
#
# SPDX-License-Identifier: Apache-2.0

"""Tests for the GARDENA smart local lawn mower platform."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.gardena_smart_local_preview.const import (
    CONF_MOWER_DURATION,
    DEFAULT_MOWER_DURATION_HOURS,
)
from custom_components.gardena_smart_local_preview.lawn_mower import GardenaMower


def _mock_device():
    device = MagicMock()
    device.id = "dev-1"
    device.serial_number = "00000001"
    device.software_version = "1.0.0"
    device.hardware_version = "1.0"
    device.model_definition.name = "Smart SILENO"
    device.model_definition.model_number = "1"
    device.valve_ids = []
    device.build_start_mowing_obj.return_value = "START_OBJ"
    device.build_stop_mowing_obj.return_value = "STOP_OBJ"
    return device


@pytest.fixture
def coordinator() -> MagicMock:
    coord = MagicMock()
    coord.connected = True
    coord.send_request = AsyncMock(return_value=[])
    return coord


def _entry(subentries: dict | None = None) -> MagicMock:
    cfg = MagicMock()
    cfg.subentries = subentries or {}
    return cfg


async def test_start_mowing_uses_default_duration(coordinator: MagicMock) -> None:
    """Starting without a configured duration falls back to the default."""
    device = _mock_device()
    coordinator.data = {device.id: device}
    mower = GardenaMower(coordinator, _entry(), device)

    await mower.async_start_mowing()

    device.build_start_mowing_obj.assert_called_once_with(
        DEFAULT_MOWER_DURATION_HOURS * 3600
    )
    coordinator.send_request.assert_awaited_once()


async def test_start_mowing_uses_configured_duration(coordinator: MagicMock) -> None:
    """A duration stored in the device subentry is used for the start command."""
    subentry = MagicMock()
    subentry.data = {"device_id": "dev-1", CONF_MOWER_DURATION: 2}
    device = _mock_device()
    coordinator.data = {device.id: device}
    mower = GardenaMower(coordinator, _entry({"sub-1": subentry}), device)

    await mower.async_start_mowing()

    device.build_start_mowing_obj.assert_called_once_with(7200)


async def test_dock_stops_mowing(coordinator: MagicMock) -> None:
    """Docking builds the stop command."""
    device = _mock_device()
    coordinator.data = {device.id: device}
    mower = GardenaMower(coordinator, _entry(), device)

    await mower.async_dock()

    device.build_stop_mowing_obj.assert_called_once_with()
