# SPDX-FileCopyrightText: 2026 GARDENA GmbH
#
# SPDX-License-Identifier: Apache-2.0

"""Tests for the GARDENA smart local button entities."""

from __future__ import annotations

from unittest.mock import AsyncMock

from gardena_smart_local_api.devices import Gen2Mower, PowerAdapter, Pump

from custom_components.gardena_smart_local_preview import button


async def test_setup_adds_identify_button_for_identify_capable_device(
    coordinator, entry, setup_platform, spec_device, sync_devices
) -> None:
    async_add_entities = await setup_platform(button, entry)
    device = spec_device(PowerAdapter, device_id="device-1")
    coordinator._devices["device-1"] = device
    sync_devices()

    async_add_entities.assert_called_once()
    (entities,), kwargs = async_add_entities.call_args
    assert len(entities) == 2
    assert isinstance(entities[0], button.GardenaIdentifyButton)
    assert isinstance(entities[1], button.GardenaClearSchedulesButton)
    assert kwargs["config_subentry_id"] is None


async def test_setup_adds_five_buttons_for_pump_in_one_call(
    coordinator, entry, setup_platform, spec_device, sync_devices
) -> None:
    async_add_entities = await setup_platform(button, entry)
    device = spec_device(Pump, device_id="device-1")
    coordinator._devices["device-1"] = device
    sync_devices()

    async_add_entities.assert_called_once()
    (entities,), _ = async_add_entities.call_args
    assert len(entities) == 5
    assert isinstance(entities[0], button.GardenaIdentifyButton)
    assert isinstance(entities[1], button.GardenaPumpResetFlowButton)
    assert isinstance(entities[2], button.GardenaPumpResetValveErrorsButton)
    assert isinstance(entities[3], button.GardenaPumpResetTemperatureMinMaxButton)
    assert isinstance(entities[4], button.GardenaClearSchedulesButton)


async def test_setup_skips_non_matching_device(
    coordinator, entry, setup_platform, spec_device, sync_devices
) -> None:
    async_add_entities = await setup_platform(button, entry)
    device = spec_device(Gen2Mower, device_id="device-1")
    coordinator._devices["device-1"] = device
    sync_devices()

    async_add_entities.assert_not_called()


async def test_setup_noop_when_coordinator_data_empty(
    coordinator, entry, setup_platform, sync_devices
) -> None:
    async_add_entities = await setup_platform(button, entry)
    sync_devices()
    async_add_entities.assert_not_called()


async def test_setup_dedups_on_repeated_firing(
    coordinator, entry, setup_platform, spec_device, sync_devices
) -> None:
    async_add_entities = await setup_platform(button, entry)
    device = spec_device(Pump, device_id="device-1")
    coordinator._devices["device-1"] = device

    sync_devices()
    sync_devices()

    async_add_entities.assert_called_once()


async def test_identify_button_press(coordinator, spec_device) -> None:
    device = spec_device(PowerAdapter, device_id="device-1")
    coordinator.send_request = AsyncMock()
    entity = button.GardenaIdentifyButton(coordinator, device)

    await entity.async_press()

    device.build_identify_obj.assert_called_once_with()
    coordinator.send_request.assert_awaited_once_with(
        "device-1", device.build_identify_obj.return_value
    )


async def test_pump_reset_flow_button_press(coordinator, spec_device) -> None:
    device = spec_device(Pump, device_id="device-1")
    coordinator.send_request = AsyncMock()
    entity = button.GardenaPumpResetFlowButton(coordinator, device)

    await entity.async_press()

    device.build_reset_flow_resettable_obj.assert_called_once_with()
    coordinator.send_request.assert_awaited_once_with(
        "device-1", device.build_reset_flow_resettable_obj.return_value
    )


async def test_pump_reset_valve_errors_button_press(coordinator, spec_device) -> None:
    device = spec_device(Pump, device_id="device-1")
    coordinator.send_request = AsyncMock()
    entity = button.GardenaPumpResetValveErrorsButton(coordinator, device)

    await entity.async_press()

    device.build_reset_all_valve_errors_obj.assert_called_once_with()
    coordinator.send_request.assert_awaited_once_with(
        "device-1", device.build_reset_all_valve_errors_obj.return_value
    )


async def test_pump_reset_temperature_min_max_button_press(
    coordinator, spec_device
) -> None:
    device = spec_device(Pump, device_id="device-1")
    coordinator.send_request = AsyncMock()
    entity = button.GardenaPumpResetTemperatureMinMaxButton(coordinator, device)

    await entity.async_press()

    device.build_reset_outlet_temperature_min_max_obj.assert_called_once_with()
    coordinator.send_request.assert_awaited_once_with(
        "device-1", device.build_reset_outlet_temperature_min_max_obj.return_value
    )
