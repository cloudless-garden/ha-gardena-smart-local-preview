# SPDX-FileCopyrightText: 2026 GARDENA GmbH
#
# SPDX-License-Identifier: Apache-2.0

"""Tests for the GARDENA smart local number entities."""

from __future__ import annotations

from unittest.mock import AsyncMock

from gardena_smart_local_api.devices import Gen1WaterControl, PowerAdapter, Pump

from custom_components.gardena_smart_local_preview import number


async def test_setup_adds_button_config_time_for_water_control(
    coordinator, entry, setup_platform, spec_device, sync_devices
) -> None:
    async_add_entities = await setup_platform(number, entry)
    device = spec_device(Gen1WaterControl, device_id="device-1")
    coordinator._devices["device-1"] = device
    sync_devices()

    async_add_entities.assert_called_once()
    (entities,), kwargs = async_add_entities.call_args
    assert len(entities) == 1
    assert isinstance(entities[0], number.GardenaButtonConfigTime)
    assert kwargs["config_subentry_id"] is None


async def test_setup_adds_two_number_entities_for_pump(
    coordinator, entry, setup_platform, spec_device, sync_devices
) -> None:
    async_add_entities = await setup_platform(number, entry)
    device = spec_device(Pump, device_id="device-1")
    coordinator._devices["device-1"] = device
    sync_devices()

    async_add_entities.assert_called_once()
    (entities,), _ = async_add_entities.call_args
    assert len(entities) == 2
    assert isinstance(entities[0], number.GardenaPumpTurnOnPressure)
    assert isinstance(entities[1], number.GardenaPumpDrippingAlert)


async def test_setup_skips_non_matching_device(
    coordinator, entry, setup_platform, spec_device, sync_devices
) -> None:
    async_add_entities = await setup_platform(number, entry)
    device = spec_device(PowerAdapter, device_id="device-1")
    coordinator._devices["device-1"] = device
    sync_devices()

    async_add_entities.assert_not_called()


async def test_setup_noop_when_coordinator_data_empty(
    coordinator, entry, setup_platform, sync_devices
) -> None:
    async_add_entities = await setup_platform(number, entry)
    sync_devices()
    async_add_entities.assert_not_called()


async def test_setup_dedups_on_repeated_firing(
    coordinator, entry, setup_platform, spec_device, sync_devices
) -> None:
    async_add_entities = await setup_platform(number, entry)
    device = spec_device(Gen1WaterControl, device_id="device-1")
    coordinator._devices["device-1"] = device

    sync_devices()
    sync_devices()

    async_add_entities.assert_called_once()


# ---------------------------------------------------------------------------
# GardenaButtonConfigTime
# ---------------------------------------------------------------------------


def test_button_config_time_native_value_converts_seconds_to_minutes(
    coordinator, spec_device, sync_devices
) -> None:
    device = spec_device(Gen1WaterControl, device_id="device-1", button_config_time=120)
    coordinator._devices["device-1"] = device
    sync_devices()
    entity = number.GardenaButtonConfigTime(coordinator, device)
    assert entity.native_value == 2


def test_button_config_time_native_value_none_when_raw_none(
    coordinator, spec_device, sync_devices
) -> None:
    device = spec_device(
        Gen1WaterControl, device_id="device-1", button_config_time=None
    )
    coordinator._devices["device-1"] = device
    sync_devices()
    entity = number.GardenaButtonConfigTime(coordinator, device)
    assert entity.native_value is None


def test_button_config_time_native_value_none_when_device_missing(
    coordinator, spec_device, sync_devices
) -> None:
    device = spec_device(Gen1WaterControl, device_id="device-1", button_config_time=120)
    sync_devices()
    entity = number.GardenaButtonConfigTime(coordinator, device)
    assert entity.native_value is None


async def test_button_config_time_set_native_value_converts_minutes_to_seconds(
    coordinator, spec_device
) -> None:
    device = spec_device(Gen1WaterControl, device_id="device-1")
    coordinator.send_request = AsyncMock()
    entity = number.GardenaButtonConfigTime(coordinator, device)

    await entity.async_set_native_value(5)

    device.build_set_button_config_time_obj.assert_called_once_with(300)
    coordinator.send_request.assert_awaited_once_with(
        "device-1", device.build_set_button_config_time_obj.return_value
    )


# ---------------------------------------------------------------------------
# GardenaPumpTurnOnPressure
# ---------------------------------------------------------------------------


def test_turn_on_pressure_native_value(coordinator, spec_device, sync_devices) -> None:
    device = spec_device(Pump, device_id="device-1", turn_on_pressure=2.5)
    coordinator._devices["device-1"] = device
    sync_devices()
    entity = number.GardenaPumpTurnOnPressure(coordinator, device)
    assert entity.native_value == 2.5


def test_turn_on_pressure_native_value_none_when_device_missing(
    coordinator, spec_device, sync_devices
) -> None:
    device = spec_device(Pump, device_id="device-1", turn_on_pressure=2.5)
    sync_devices()
    entity = number.GardenaPumpTurnOnPressure(coordinator, device)
    assert entity.native_value is None


async def test_turn_on_pressure_set_native_value(coordinator, spec_device) -> None:
    device = spec_device(Pump, device_id="device-1")
    coordinator.send_request = AsyncMock()
    entity = number.GardenaPumpTurnOnPressure(coordinator, device)

    await entity.async_set_native_value(3.2)

    device.build_set_turn_on_pressure_obj.assert_called_once_with(3.2)
    coordinator.send_request.assert_awaited_once_with(
        "device-1", device.build_set_turn_on_pressure_obj.return_value
    )


# ---------------------------------------------------------------------------
# GardenaPumpDrippingAlert
# ---------------------------------------------------------------------------


def test_dripping_alert_native_value(coordinator, spec_device, sync_devices) -> None:
    device = spec_device(Pump, device_id="device-1", dripping_alert=120)
    coordinator._devices["device-1"] = device
    sync_devices()
    entity = number.GardenaPumpDrippingAlert(coordinator, device)
    assert entity.native_value == 120


def test_dripping_alert_native_value_none_when_device_missing(
    coordinator, spec_device, sync_devices
) -> None:
    device = spec_device(Pump, device_id="device-1", dripping_alert=120)
    sync_devices()
    entity = number.GardenaPumpDrippingAlert(coordinator, device)
    assert entity.native_value is None


async def test_dripping_alert_set_native_value(coordinator, spec_device) -> None:
    device = spec_device(Pump, device_id="device-1")
    coordinator.send_request = AsyncMock()
    entity = number.GardenaPumpDrippingAlert(coordinator, device)

    await entity.async_set_native_value(120.0)

    device.build_set_dripping_alert_obj.assert_called_once_with(120)
    coordinator.send_request.assert_awaited_once_with(
        "device-1", device.build_set_dripping_alert_obj.return_value
    )
