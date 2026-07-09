# SPDX-FileCopyrightText: 2026 GARDENA GmbH
#
# SPDX-License-Identifier: Apache-2.0

"""Tests for the GARDENA smart local frost-warning binary sensor."""

from __future__ import annotations

from gardena_smart_local_api.devices import Gen1WaterControl, PowerAdapter

from custom_components.gardena_smart_local_preview import binary_sensor


async def test_setup_adds_frost_sensor_for_matching_device(
    coordinator, entry, setup_platform, spec_device, sync_devices
) -> None:
    async_add_entities = await setup_platform(binary_sensor, entry)
    device = spec_device(Gen1WaterControl, device_id="device-1")
    coordinator._devices["device-1"] = device
    sync_devices()

    async_add_entities.assert_called_once()
    (entities,), kwargs = async_add_entities.call_args
    assert len(entities) == 1
    assert isinstance(entities[0], binary_sensor.GardenaFrostWarningSensor)
    assert kwargs["config_subentry_id"] is None


async def test_setup_skips_non_matching_device(
    coordinator, entry, setup_platform, spec_device, sync_devices
) -> None:
    async_add_entities = await setup_platform(binary_sensor, entry)
    device = spec_device(PowerAdapter, device_id="device-1")
    coordinator._devices["device-1"] = device
    sync_devices()

    async_add_entities.assert_not_called()


async def test_setup_noop_when_coordinator_data_empty(
    coordinator, entry, setup_platform, sync_devices
) -> None:
    async_add_entities = await setup_platform(binary_sensor, entry)
    sync_devices()
    async_add_entities.assert_not_called()


async def test_setup_dedups_on_repeated_firing(
    coordinator, entry, setup_platform, spec_device, sync_devices
) -> None:
    async_add_entities = await setup_platform(binary_sensor, entry)
    device = spec_device(Gen1WaterControl, device_id="device-1")
    coordinator._devices["device-1"] = device

    sync_devices()
    sync_devices()

    async_add_entities.assert_called_once()


def test_is_on_true(coordinator, spec_device, sync_devices) -> None:
    device = spec_device(Gen1WaterControl, device_id="device-1", has_frost_warning=True)
    coordinator._devices["device-1"] = device
    sync_devices()
    entity = binary_sensor.GardenaFrostWarningSensor(coordinator, device)
    assert entity.is_on is True


def test_is_on_false(coordinator, spec_device, sync_devices) -> None:
    device = spec_device(
        Gen1WaterControl, device_id="device-1", has_frost_warning=False
    )
    coordinator._devices["device-1"] = device
    sync_devices()
    entity = binary_sensor.GardenaFrostWarningSensor(coordinator, device)
    assert entity.is_on is False


def test_is_on_none_when_device_missing(coordinator, spec_device, sync_devices) -> None:
    device = spec_device(Gen1WaterControl, device_id="device-1", has_frost_warning=True)
    sync_devices()
    entity = binary_sensor.GardenaFrostWarningSensor(coordinator, device)
    assert entity.is_on is None
