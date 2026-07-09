# SPDX-FileCopyrightText: 2026 GARDENA GmbH
#
# SPDX-License-Identifier: Apache-2.0

"""Tests for the GARDENA smart local lawn mower entity."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from gardena_smart_local_api.devices import (
    Gen1Mower1,
    Gen2Mower,
    MowerState,
    PowerAdapter,
)
from homeassistant.components.lawn_mower import (
    LawnMowerActivity,
    LawnMowerEntityFeature,
)

from custom_components.gardena_smart_local_preview import lawn_mower


async def test_setup_adds_mower_for_matching_device(
    coordinator, entry, setup_platform, spec_device, sync_devices
) -> None:
    async_add_entities = await setup_platform(lawn_mower, entry)
    device = spec_device(Gen1Mower1, device_id="device-1")
    coordinator._devices["device-1"] = device
    sync_devices()

    async_add_entities.assert_called_once()
    (entities,), kwargs = async_add_entities.call_args
    assert len(entities) == 1
    assert isinstance(entities[0], lawn_mower.GardenaMower)
    assert kwargs["config_subentry_id"] is None


async def test_setup_skips_non_matching_device(
    coordinator, entry, setup_platform, spec_device, sync_devices
) -> None:
    async_add_entities = await setup_platform(lawn_mower, entry)
    device = spec_device(PowerAdapter, device_id="device-1")
    coordinator._devices["device-1"] = device
    sync_devices()

    async_add_entities.assert_not_called()


async def test_setup_noop_when_coordinator_data_empty(
    coordinator, entry, setup_platform, sync_devices
) -> None:
    async_add_entities = await setup_platform(lawn_mower, entry)
    sync_devices()
    async_add_entities.assert_not_called()


async def test_setup_dedups_on_repeated_firing(
    coordinator, entry, setup_platform, spec_device, sync_devices
) -> None:
    async_add_entities = await setup_platform(lawn_mower, entry)
    device = spec_device(Gen1Mower1, device_id="device-1")
    coordinator._devices["device-1"] = device

    sync_devices()
    sync_devices()

    async_add_entities.assert_called_once()


def test_gen1_mower_has_no_pause_feature(coordinator, spec_device) -> None:
    device = spec_device(Gen1Mower1, device_id="device-1")
    entity = lawn_mower.GardenaMower(coordinator, device)
    assert not entity.supported_features & LawnMowerEntityFeature.PAUSE


def test_gen2_mower_has_pause_feature(coordinator, spec_device) -> None:
    device = spec_device(Gen2Mower, device_id="device-1")
    entity = lawn_mower.GardenaMower(coordinator, device)
    assert entity.supported_features & LawnMowerEntityFeature.PAUSE


@pytest.mark.parametrize(
    ("state", "expected"),
    [
        (MowerState.CHARGING, LawnMowerActivity.DOCKED),
        (MowerState.PARKED, LawnMowerActivity.DOCKED),
        (MowerState.LEAVING, LawnMowerActivity.MOWING),
        (MowerState.MOWING, LawnMowerActivity.MOWING),
        (MowerState.PAUSED, LawnMowerActivity.PAUSED),
        (MowerState.RETURNING, LawnMowerActivity.RETURNING),
        (MowerState.UNKNOWN, LawnMowerActivity.ERROR),
    ],
)
def test_activity_maps_mower_state(coordinator, spec_device, state, expected) -> None:
    device = spec_device(Gen1Mower1, device_id="device-1", state=state)
    entity = lawn_mower.GardenaMower(coordinator, device)
    assert entity.activity == expected


async def test_async_start_mowing(coordinator, spec_device) -> None:
    device = spec_device(Gen1Mower1, device_id="device-1")
    coordinator.send_request = AsyncMock()
    entity = lawn_mower.GardenaMower(coordinator, device)

    await entity.async_start_mowing()

    device.build_start_mowing_obj.assert_called_once_with(28800)
    coordinator.send_request.assert_awaited_once_with(
        "device-1", device.build_start_mowing_obj.return_value
    )


async def test_async_dock(coordinator, spec_device) -> None:
    device = spec_device(Gen1Mower1, device_id="device-1")
    coordinator.send_request = AsyncMock()
    entity = lawn_mower.GardenaMower(coordinator, device)

    await entity.async_dock()

    device.build_stop_mowing_obj.assert_called_once_with()
    coordinator.send_request.assert_awaited_once_with(
        "device-1", device.build_stop_mowing_obj.return_value
    )


async def test_async_pause_on_gen2_device(coordinator, spec_device) -> None:
    device = spec_device(Gen2Mower, device_id="device-1")
    coordinator.send_request = AsyncMock()
    entity = lawn_mower.GardenaMower(coordinator, device)

    await entity.async_pause()

    device.build_pause_mowing_obj.assert_called_once_with()
    coordinator.send_request.assert_awaited_once_with(
        "device-1", device.build_pause_mowing_obj.return_value
    )


async def test_async_pause_on_gen1_device_is_noop(coordinator, spec_device) -> None:
    device = spec_device(Gen1Mower1, device_id="device-1")
    coordinator.send_request = AsyncMock()
    entity = lawn_mower.GardenaMower(coordinator, device)

    await entity.async_pause()

    coordinator.send_request.assert_not_awaited()
