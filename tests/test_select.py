# SPDX-FileCopyrightText: 2026 GARDENA GmbH
#
# SPDX-License-Identifier: Apache-2.0

"""Tests for the GARDENA smart local pump operating-mode select entity."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from gardena_smart_local_api.devices import PowerAdapter, Pump
from gardena_smart_local_api.devices.irrigation import PumpOperatingMode

from custom_components.gardena_smart_local_preview import select


async def test_setup_adds_select_for_pump(
    coordinator, entry, setup_platform, spec_device, sync_devices
) -> None:
    async_add_entities = await setup_platform(select, entry)
    device = spec_device(Pump, device_id="device-1")
    coordinator._devices["device-1"] = device
    sync_devices()

    async_add_entities.assert_called_once()
    (entities,), kwargs = async_add_entities.call_args
    assert len(entities) == 1
    assert isinstance(entities[0], select.GardenaPumpOperatingModeSelect)
    assert kwargs["config_subentry_id"] is None


async def test_setup_skips_non_pump_device(
    coordinator, entry, setup_platform, spec_device, sync_devices
) -> None:
    async_add_entities = await setup_platform(select, entry)
    device = spec_device(PowerAdapter, device_id="device-1")
    coordinator._devices["device-1"] = device
    sync_devices()

    async_add_entities.assert_not_called()


async def test_setup_noop_when_coordinator_data_empty(
    coordinator, entry, setup_platform, sync_devices
) -> None:
    async_add_entities = await setup_platform(select, entry)
    sync_devices()
    async_add_entities.assert_not_called()


async def test_setup_dedups_on_repeated_firing(
    coordinator, entry, setup_platform, spec_device, sync_devices
) -> None:
    async_add_entities = await setup_platform(select, entry)
    device = spec_device(Pump, device_id="device-1")
    coordinator._devices["device-1"] = device

    sync_devices()
    sync_devices()

    async_add_entities.assert_called_once()


def test_options_are_scheduled_and_automatic(coordinator, spec_device) -> None:
    device = spec_device(Pump, device_id="device-1")
    entity = select.GardenaPumpOperatingModeSelect(coordinator, device)
    assert entity.options == ["scheduled", "automatic"]


def test_current_option_scheduled(coordinator, spec_device, sync_devices) -> None:
    device = spec_device(
        Pump, device_id="device-1", operating_mode=PumpOperatingMode.SCHEDULED
    )
    coordinator._devices["device-1"] = device
    sync_devices()
    entity = select.GardenaPumpOperatingModeSelect(coordinator, device)
    assert entity.current_option == "scheduled"


def test_current_option_automatic(coordinator, spec_device, sync_devices) -> None:
    device = spec_device(
        Pump, device_id="device-1", operating_mode=PumpOperatingMode.AUTOMATIC
    )
    coordinator._devices["device-1"] = device
    sync_devices()
    entity = select.GardenaPumpOperatingModeSelect(coordinator, device)
    assert entity.current_option == "automatic"


def test_current_option_none_when_mode_none(
    coordinator, spec_device, sync_devices
) -> None:
    device = spec_device(Pump, device_id="device-1", operating_mode=None)
    coordinator._devices["device-1"] = device
    sync_devices()
    entity = select.GardenaPumpOperatingModeSelect(coordinator, device)
    assert entity.current_option is None


def test_current_option_none_when_mode_unmapped(
    coordinator, spec_device, sync_devices
) -> None:
    device = spec_device(Pump, device_id="device-1", operating_mode=object())
    coordinator._devices["device-1"] = device
    sync_devices()
    entity = select.GardenaPumpOperatingModeSelect(coordinator, device)
    assert entity.current_option is None


def test_current_option_none_when_device_missing(
    coordinator, spec_device, sync_devices
) -> None:
    device = spec_device(
        Pump, device_id="device-1", operating_mode=PumpOperatingMode.SCHEDULED
    )
    sync_devices()
    entity = select.GardenaPumpOperatingModeSelect(coordinator, device)
    assert entity.current_option is None


async def test_select_option_scheduled(coordinator, spec_device) -> None:
    device = spec_device(Pump, device_id="device-1")
    coordinator.send_request = AsyncMock()
    entity = select.GardenaPumpOperatingModeSelect(coordinator, device)

    await entity.async_select_option("scheduled")

    device.build_set_operating_mode_obj.assert_called_once_with(
        PumpOperatingMode.SCHEDULED
    )
    coordinator.send_request.assert_awaited_once_with(
        "device-1", device.build_set_operating_mode_obj.return_value
    )


async def test_select_option_automatic(coordinator, spec_device) -> None:
    device = spec_device(Pump, device_id="device-1")
    coordinator.send_request = AsyncMock()
    entity = select.GardenaPumpOperatingModeSelect(coordinator, device)

    await entity.async_select_option("automatic")

    device.build_set_operating_mode_obj.assert_called_once_with(
        PumpOperatingMode.AUTOMATIC
    )


async def test_select_option_invalid_raises_key_error(coordinator, spec_device) -> None:
    device = spec_device(Pump, device_id="device-1")
    coordinator.send_request = AsyncMock()
    entity = select.GardenaPumpOperatingModeSelect(coordinator, device)

    with pytest.raises(KeyError):
        await entity.async_select_option("bogus")
