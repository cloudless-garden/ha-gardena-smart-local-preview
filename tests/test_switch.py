# SPDX-FileCopyrightText: 2026 GARDENA GmbH
#
# SPDX-License-Identifier: Apache-2.0

"""Tests for the GARDENA smart local switch entities."""

from __future__ import annotations

from unittest.mock import AsyncMock

from gardena_smart_local_api.devices import Gen1WaterControl, PowerAdapter, Pump

from custom_components.gardena_smart_local_preview import switch


async def test_setup_adds_power_switch_for_power_adapter(
    coordinator, entry, setup_platform, spec_device, sync_devices
) -> None:
    async_add_entities = await setup_platform(switch, entry)
    device = spec_device(PowerAdapter, device_id="device-1")
    coordinator._devices["device-1"] = device
    sync_devices()

    async_add_entities.assert_called_once()
    (entities,), kwargs = async_add_entities.call_args
    assert len(entities) == 1
    assert isinstance(entities[0], switch.GardenaPowerSwitch)
    assert kwargs["config_subentry_id"] is None


async def test_setup_adds_pump_switch_for_pump(
    coordinator, entry, setup_platform, spec_device, sync_devices
) -> None:
    async_add_entities = await setup_platform(switch, entry)
    device = spec_device(Pump, device_id="device-1")
    coordinator._devices["device-1"] = device
    sync_devices()

    async_add_entities.assert_called_once()
    (entities,), _ = async_add_entities.call_args
    assert len(entities) == 1
    assert isinstance(entities[0], switch.GardenaPumpSwitch)


async def test_setup_skips_non_matching_device(
    coordinator, entry, setup_platform, spec_device, sync_devices
) -> None:
    async_add_entities = await setup_platform(switch, entry)
    device = spec_device(Gen1WaterControl, device_id="device-1")
    coordinator._devices["device-1"] = device
    sync_devices()

    async_add_entities.assert_not_called()


async def test_setup_noop_when_coordinator_data_empty(
    coordinator, entry, setup_platform, sync_devices
) -> None:
    async_add_entities = await setup_platform(switch, entry)
    sync_devices()
    async_add_entities.assert_not_called()


async def test_setup_dedups_on_repeated_firing(
    coordinator, entry, setup_platform, spec_device, sync_devices
) -> None:
    async_add_entities = await setup_platform(switch, entry)
    device = spec_device(PowerAdapter, device_id="device-1")
    coordinator._devices["device-1"] = device

    sync_devices()
    sync_devices()

    async_add_entities.assert_called_once()


def test_power_switch_device_class_outlet(coordinator, spec_device) -> None:
    device = spec_device(PowerAdapter, device_id="device-1")
    entity = switch.GardenaPowerSwitch(coordinator, device)
    assert entity.device_class == "outlet"


def test_pump_switch_has_no_device_class(coordinator, spec_device) -> None:
    device = spec_device(Pump, device_id="device-1")
    entity = switch.GardenaPumpSwitch(coordinator, device)
    assert entity.device_class is None


def test_power_switch_is_on_true(coordinator, spec_device, sync_devices) -> None:
    device = spec_device(PowerAdapter, device_id="device-1", is_output_enabled=True)
    coordinator._devices["device-1"] = device
    sync_devices()
    entity = switch.GardenaPowerSwitch(coordinator, device)
    assert entity.is_on is True


def test_power_switch_is_on_false(coordinator, spec_device, sync_devices) -> None:
    device = spec_device(PowerAdapter, device_id="device-1", is_output_enabled=False)
    coordinator._devices["device-1"] = device
    sync_devices()
    entity = switch.GardenaPowerSwitch(coordinator, device)
    assert entity.is_on is False


def test_power_switch_is_on_none_when_missing(
    coordinator, spec_device, sync_devices
) -> None:
    device = spec_device(PowerAdapter, device_id="device-1", is_output_enabled=True)
    sync_devices()
    entity = switch.GardenaPowerSwitch(coordinator, device)
    assert entity.is_on is None


def test_pump_switch_is_on_true(coordinator, spec_device, sync_devices) -> None:
    device = spec_device(Pump, device_id="device-1", is_running=True)
    coordinator._devices["device-1"] = device
    sync_devices()
    entity = switch.GardenaPumpSwitch(coordinator, device)
    assert entity.is_on is True


def test_pump_switch_is_on_false(coordinator, spec_device, sync_devices) -> None:
    device = spec_device(Pump, device_id="device-1", is_running=False)
    coordinator._devices["device-1"] = device
    sync_devices()
    entity = switch.GardenaPumpSwitch(coordinator, device)
    assert entity.is_on is False


def test_pump_switch_is_on_none_when_missing(
    coordinator, spec_device, sync_devices
) -> None:
    device = spec_device(Pump, device_id="device-1", is_running=True)
    sync_devices()
    entity = switch.GardenaPumpSwitch(coordinator, device)
    assert entity.is_on is None


async def test_power_switch_turn_on(coordinator, spec_device) -> None:
    device = spec_device(PowerAdapter, device_id="device-1")
    coordinator.send_request = AsyncMock()
    entity = switch.GardenaPowerSwitch(coordinator, device)

    await entity.async_turn_on()

    device.build_enable_output_obj.assert_called_once_with(
        switch.DEFAULT_ON_DURATION_SECONDS
    )
    coordinator.send_request.assert_awaited_once_with(
        "device-1", device.build_enable_output_obj.return_value
    )


async def test_power_switch_turn_off(coordinator, spec_device) -> None:
    device = spec_device(PowerAdapter, device_id="device-1")
    coordinator.send_request = AsyncMock()
    entity = switch.GardenaPowerSwitch(coordinator, device)

    await entity.async_turn_off()

    device.build_disable_output_obj.assert_called_once_with()
    coordinator.send_request.assert_awaited_once_with(
        "device-1", device.build_disable_output_obj.return_value
    )


async def test_pump_switch_turn_on(coordinator, spec_device) -> None:
    device = spec_device(Pump, device_id="device-1")
    coordinator.send_request = AsyncMock()
    entity = switch.GardenaPumpSwitch(coordinator, device)

    await entity.async_turn_on()

    device.build_start_obj.assert_called_once_with(switch.DEFAULT_ON_DURATION_SECONDS)
    coordinator.send_request.assert_awaited_once_with(
        "device-1", device.build_start_obj.return_value
    )


async def test_pump_switch_turn_off(coordinator, spec_device) -> None:
    device = spec_device(Pump, device_id="device-1")
    coordinator.send_request = AsyncMock()
    entity = switch.GardenaPumpSwitch(coordinator, device)

    await entity.async_turn_off()

    device.build_stop_obj.assert_called_once_with()
    coordinator.send_request.assert_awaited_once_with(
        "device-1", device.build_stop_obj.return_value
    )
