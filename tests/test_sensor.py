# SPDX-FileCopyrightText: 2026 GARDENA GmbH
#
# SPDX-License-Identifier: Apache-2.0

"""Tests for the GARDENA smart local sensor entities."""

from __future__ import annotations

import pytest
from gardena_smart_local_api.devices import (
    Gen1WaterControl,
    Gen2IrrigationControl,
    Pump,
    PumpState,
    Sensor1,
)

from custom_components.gardena_smart_local_preview import sensor


def _identity(value):
    return value


# (entity class, spec class, device attr, raw value, cast applied by native_value)
SENSOR_TABLE = [
    (sensor.GardenaTemperatureSensor, Gen1WaterControl, "temperature", 21, float),
    (sensor.GardenaBatterySensor, Gen1WaterControl, "battery_level", 55, float),
    (
        sensor.GardenaRfLinkQualitySensor,
        Gen1WaterControl,
        "rf_link_quality",
        80,
        _identity,
    ),
    (sensor.GardenaSoilMoistureSensor, Sensor1, "soil_moisture", 42, float),
    (sensor.GardenaLightSensor, Sensor1, "light", 1000, float),
    (sensor.GardenaPumpPressureSensor, Pump, "outlet_pressure", 1.5, _identity),
    (sensor.GardenaPumpTemperatureSensor, Pump, "outlet_temperature", 18, float),
    (sensor.GardenaPumpFlowRateSensor, Pump, "flow_rate", 120, float),
    (sensor.GardenaPumpFlowTotalSensor, Pump, "flow_total", 5, float),
    (sensor.GardenaPumpFlowSinceResetSensor, Pump, "flow_since_last_reset", 2, float),
    (
        sensor.GardenaPumpStateSensor,
        Pump,
        "pump_state",
        PumpState.PUMP_IS_JUST_STARTING,
        str,
    ),
]


@pytest.mark.parametrize(
    ("entity_cls", "spec_cls", "attr", "raw", "cast"), SENSOR_TABLE
)
def test_native_value_normal(
    coordinator, spec_device, sync_devices, entity_cls, spec_cls, attr, raw, cast
) -> None:
    device = spec_device(spec_cls, device_id="device-1", **{attr: raw})
    coordinator._devices["device-1"] = device
    sync_devices()
    entity = entity_cls(coordinator, device)
    assert entity.native_value == cast(raw)


@pytest.mark.parametrize(
    ("entity_cls", "spec_cls", "attr", "raw", "cast"), SENSOR_TABLE
)
def test_native_value_none_when_raw_none(
    coordinator, spec_device, sync_devices, entity_cls, spec_cls, attr, raw, cast
) -> None:
    device = spec_device(spec_cls, device_id="device-1", **{attr: None})
    coordinator._devices["device-1"] = device
    sync_devices()
    entity = entity_cls(coordinator, device)
    assert entity.native_value is None


@pytest.mark.parametrize(
    ("entity_cls", "spec_cls", "attr", "raw", "cast"), SENSOR_TABLE
)
def test_native_value_none_when_device_missing(
    coordinator, spec_device, sync_devices, entity_cls, spec_cls, attr, raw, cast
) -> None:
    device = spec_device(spec_cls, device_id="device-1", **{attr: raw})
    sync_devices()
    entity = entity_cls(coordinator, device)
    assert entity.native_value is None


# ---------------------------------------------------------------------------
# Setup / dynamic-add fan-out
# ---------------------------------------------------------------------------


async def test_setup_water_control_gets_five_sensors(
    coordinator, entry, setup_platform, spec_device, sync_devices
) -> None:
    async_add_entities = await setup_platform(sensor, entry)
    device = spec_device(Gen1WaterControl, device_id="device-1")
    coordinator._devices["device-1"] = device
    sync_devices()

    async_add_entities.assert_called_once()
    (entities,), kwargs = async_add_entities.call_args
    assert len(entities) == 5
    assert {type(e) for e in entities} == {
        sensor.GardenaTemperatureSensor,
        sensor.GardenaBatterySensor,
        sensor.GardenaRfLinkQualitySensor,
        sensor.GardenaScheduleCountSensor,
        sensor.GardenaFirmwareUpdateStateSensor,
    }
    assert kwargs["config_subentry_id"] is None


async def test_setup_sensor1_gets_six_sensors_in_one_call(
    coordinator, entry, setup_platform, spec_device, sync_devices
) -> None:
    async_add_entities = await setup_platform(sensor, entry)
    device = spec_device(Sensor1, device_id="device-1")
    coordinator._devices["device-1"] = device
    sync_devices()

    async_add_entities.assert_called_once()
    (entities,), _ = async_add_entities.call_args
    assert len(entities) == 6
    assert {type(e) for e in entities} == {
        sensor.GardenaTemperatureSensor,
        sensor.GardenaSoilMoistureSensor,
        sensor.GardenaLightSensor,
        sensor.GardenaBatterySensor,
        sensor.GardenaRfLinkQualitySensor,
        sensor.GardenaFirmwareUpdateStateSensor,
    }


async def test_setup_pump_gets_nine_sensors_in_one_call(
    coordinator, entry, setup_platform, spec_device, sync_devices
) -> None:
    async_add_entities = await setup_platform(sensor, entry)
    device = spec_device(Pump, device_id="device-1")
    coordinator._devices["device-1"] = device
    sync_devices()

    async_add_entities.assert_called_once()
    (entities,), _ = async_add_entities.call_args
    assert len(entities) == 9
    assert {type(e) for e in entities} == {
        sensor.GardenaRfLinkQualitySensor,
        sensor.GardenaPumpPressureSensor,
        sensor.GardenaPumpTemperatureSensor,
        sensor.GardenaPumpFlowRateSensor,
        sensor.GardenaPumpFlowTotalSensor,
        sensor.GardenaPumpFlowSinceResetSensor,
        sensor.GardenaPumpStateSensor,
        sensor.GardenaScheduleCountSensor,
        sensor.GardenaFirmwareUpdateStateSensor,
    }


async def test_setup_adds_only_firmware_sensor_for_device_matching_no_other_gates(
    coordinator, entry, setup_platform, spec_device, sync_devices
) -> None:
    async_add_entities = await setup_platform(sensor, entry)
    device = spec_device(Gen2IrrigationControl, device_id="device-1")
    coordinator._devices["device-1"] = device
    sync_devices()

    async_add_entities.assert_called_once()
    (entities,), _ = async_add_entities.call_args
    assert len(entities) == 1
    assert isinstance(entities[0], sensor.GardenaFirmwareUpdateStateSensor)


async def test_setup_noop_when_coordinator_data_empty(
    coordinator, entry, setup_platform, sync_devices
) -> None:
    async_add_entities = await setup_platform(sensor, entry)
    sync_devices()
    async_add_entities.assert_not_called()


async def test_setup_dedups_on_repeated_firing(
    coordinator, entry, setup_platform, spec_device, sync_devices
) -> None:
    async_add_entities = await setup_platform(sensor, entry)
    device = spec_device(Gen1WaterControl, device_id="device-1")
    coordinator._devices["device-1"] = device

    sync_devices()
    sync_devices()

    async_add_entities.assert_called_once()
