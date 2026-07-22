# SPDX-FileCopyrightText: 2026 GARDENA GmbH
#
# SPDX-License-Identifier: Apache-2.0

"""Tests for the GARDENA smart local valve entity."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from gardena_smart_local_api.devices import (
    Gen1IrrigationControl,
    Gen1WaterControl,
    Pump,
)

from custom_components.gardena_smart_local_preview import valve


async def test_setup_adds_single_valve_for_water_control(
    coordinator, entry, setup_platform, spec_device, sync_devices
) -> None:
    async_add_entities = await setup_platform(valve, entry)
    device = spec_device(Gen1WaterControl, device_id="device-1", valve_ids=[0])
    coordinator._devices["device-1"] = device
    sync_devices()

    async_add_entities.assert_called_once()
    (entities,), kwargs = async_add_entities.call_args
    assert len(entities) == 1
    assert isinstance(entities[0], valve.GardenaValve)
    assert entities[0].name is None
    assert kwargs["config_subentry_id"] is None


async def test_setup_adds_six_valves_for_irrigation_control(
    coordinator, entry, setup_platform, spec_device, sync_devices
) -> None:
    async_add_entities = await setup_platform(valve, entry)
    device = spec_device(
        Gen1IrrigationControl, device_id="device-1", valve_ids=list(range(6))
    )
    coordinator._devices["device-1"] = device
    sync_devices()

    async_add_entities.assert_called_once()
    (entities,), _ = async_add_entities.call_args
    assert len(entities) == 6
    for i, entity in enumerate(entities):
        assert entity.name == f"Valve {i + 1}"


async def test_setup_skips_non_matching_device(
    coordinator, entry, setup_platform, spec_device, sync_devices
) -> None:
    async_add_entities = await setup_platform(valve, entry)
    device = spec_device(Pump, device_id="device-1")
    coordinator._devices["device-1"] = device
    sync_devices()

    async_add_entities.assert_not_called()


async def test_setup_noop_when_coordinator_data_empty(
    coordinator, entry, setup_platform, sync_devices
) -> None:
    async_add_entities = await setup_platform(valve, entry)
    sync_devices()
    async_add_entities.assert_not_called()


async def test_setup_dedups_on_repeated_firing(
    coordinator, entry, setup_platform, spec_device, sync_devices
) -> None:
    async_add_entities = await setup_platform(valve, entry)
    device = spec_device(Gen1WaterControl, device_id="device-1", valve_ids=[0])
    coordinator._devices["device-1"] = device

    sync_devices()
    sync_devices()

    async_add_entities.assert_called_once()


def test_is_closed_true_when_valve_open(coordinator, spec_device, sync_devices) -> None:
    device = spec_device(Gen1WaterControl, device_id="device-1", valve_ids=[0])
    device.is_valve_open.return_value = True
    coordinator._devices["device-1"] = device
    sync_devices()
    entity = valve.GardenaValve(coordinator, device, valve_id=0)
    assert entity.is_closed is False


def test_is_closed_true_when_valve_not_open(
    coordinator, spec_device, sync_devices
) -> None:
    device = spec_device(Gen1WaterControl, device_id="device-1", valve_ids=[0])
    device.is_valve_open.return_value = False
    coordinator._devices["device-1"] = device
    sync_devices()
    entity = valve.GardenaValve(coordinator, device, valve_id=0)
    assert entity.is_closed is True


def test_is_closed_none_when_valve_state_unknown(
    coordinator, spec_device, sync_devices
) -> None:
    device = spec_device(Gen1WaterControl, device_id="device-1", valve_ids=[0])
    device.is_valve_open.return_value = None
    coordinator._devices["device-1"] = device
    sync_devices()
    entity = valve.GardenaValve(coordinator, device, valve_id=0)
    assert entity.is_closed is None


def test_is_closed_none_when_device_missing(
    coordinator, spec_device, sync_devices
) -> None:
    device = spec_device(Gen1WaterControl, device_id="device-1", valve_ids=[0])
    sync_devices()
    entity = valve.GardenaValve(coordinator, device, valve_id=0)
    assert entity.is_closed is None


@pytest.mark.parametrize("valve_id", [0, 3])
async def test_async_open_valve(coordinator, spec_device, valve_id) -> None:
    device = spec_device(
        Gen1IrrigationControl, device_id="device-1", valve_ids=list(range(6))
    )
    coordinator.send_request = AsyncMock()
    entity = valve.GardenaValve(coordinator, device, valve_id=valve_id)

    await entity.async_open_valve()

    device.build_open_valve_obj.assert_called_once_with(valve_id, 1800)
    coordinator.send_request.assert_awaited_once_with(
        "device-1", device.build_open_valve_obj.return_value
    )


@pytest.mark.parametrize("valve_id", [0, 3])
async def test_async_close_valve(coordinator, spec_device, valve_id) -> None:
    device = spec_device(
        Gen1IrrigationControl, device_id="device-1", valve_ids=list(range(6))
    )
    coordinator.send_request = AsyncMock()
    entity = valve.GardenaValve(coordinator, device, valve_id=valve_id)

    await entity.async_close_valve()

    device.build_close_valve_obj.assert_called_once_with(valve_id)
    coordinator.send_request.assert_awaited_once_with(
        "device-1", device.build_close_valve_obj.return_value
    )
