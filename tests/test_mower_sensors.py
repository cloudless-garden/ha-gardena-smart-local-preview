# SPDX-FileCopyrightText: 2026 GARDENA GmbH
#
# SPDX-License-Identifier: Apache-2.0

"""Tests for the mower-specific sensor entities."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest
from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass
from homeassistant.const import EntityCategory, UnitOfTime

from custom_components.gardena_smart_local_preview import sensor
from custom_components.gardena_smart_local_preview.sensor import (
    MOWER_STATISTICS,
    GardenaMowerLastErrorSensor,
    GardenaMowerStatisticSensor,
)
from tests.common import make_gen1_mower

LEMONBEAT = {
    "last_error_code": {"vi": 15},
    "timestamp_last_error_code": {"vo": "arPA3g=="},
    "cutting_time": {"vi": 1269},
    "running_time": {"vi": 1345},
    "charging_cycles": {"vi": 933},
    "collisions": {"vi": 3120},
}


@pytest.fixture
def mower_device():
    return make_gen1_mower(LEMONBEAT)


@pytest.fixture
def mower_coordinator(coordinator: MagicMock, mower_device) -> MagicMock:
    coordinator.data = {mower_device.id: mower_device}
    return coordinator


def test_last_error_sensor_names_known_code(
    mower_coordinator: MagicMock, mower_device
) -> None:
    entity = GardenaMowerLastErrorSensor(mower_coordinator, mower_device)

    assert entity.unique_id == "dev-1_last_error"
    assert entity.translation_key == "last_error"
    assert entity.entity_category == EntityCategory.DIAGNOSTIC
    assert entity.native_value == "lifted"
    assert entity.extra_state_attributes == {
        "raw_code": 15,
        "timestamp": datetime(2026, 9, 23, 10, 6, 54, tzinfo=UTC),
    }


def test_last_error_sensor_exposes_unknown_code_raw(coordinator: MagicMock) -> None:
    device = make_gen1_mower({"last_error_code": {"vi": 999}})
    coordinator.data = {device.id: device}
    entity = GardenaMowerLastErrorSensor(coordinator, device)

    assert entity.native_value == "code_999"
    assert entity.extra_state_attributes["raw_code"] == 999


def test_last_error_sensor_reports_no_message_for_code_zero(
    coordinator: MagicMock,
) -> None:
    device = make_gen1_mower({"last_error_code": {"vi": 0}})
    coordinator.data = {device.id: device}
    entity = GardenaMowerLastErrorSensor(coordinator, device)

    assert entity.native_value == "no_message"
    assert entity.extra_state_attributes == {"raw_code": 0, "timestamp": None}


def test_last_error_sensor_is_unknown_when_device_is_gone(
    mower_coordinator: MagicMock, mower_device
) -> None:
    entity = GardenaMowerLastErrorSensor(mower_coordinator, mower_device)
    mower_coordinator.data = {}

    assert entity.native_value is None
    assert entity.extra_state_attributes == {"raw_code": None, "timestamp": None}


def test_statistics_cover_the_four_mower_counters() -> None:
    assert [d.key for d in MOWER_STATISTICS] == [
        "cutting_time",
        "running_time",
        "charging_cycles",
        "collisions",
    ]


@pytest.mark.parametrize(
    ("key", "value", "unit", "device_class"),
    [
        ("cutting_time", 1269, UnitOfTime.HOURS, SensorDeviceClass.DURATION),
        ("running_time", 1345, UnitOfTime.HOURS, SensorDeviceClass.DURATION),
        ("charging_cycles", 933, None, None),
        ("collisions", 3120, None, None),
    ],
)
def test_statistic_sensor_reads_its_counter(
    mower_coordinator: MagicMock,
    mower_device,
    key: str,
    value: int,
    unit: str | None,
    device_class: SensorDeviceClass | None,
) -> None:
    description = next(d for d in MOWER_STATISTICS if d.key == key)
    entity = GardenaMowerStatisticSensor(mower_coordinator, mower_device, description)

    assert entity.unique_id == f"dev-1_{key}"
    assert entity.translation_key == key
    assert entity.native_value == value
    assert entity.native_unit_of_measurement == unit
    assert entity.device_class == device_class
    assert entity.state_class == SensorStateClass.TOTAL_INCREASING
    assert entity.entity_category == EntityCategory.DIAGNOSTIC


def test_statistic_sensor_is_unknown_when_not_reported(coordinator: MagicMock) -> None:
    device = make_gen1_mower()
    coordinator.data = {device.id: device}
    entity = GardenaMowerStatisticSensor(coordinator, device, MOWER_STATISTICS[0])

    assert entity.native_value is None


def _added_unique_ids(async_add_entities: MagicMock) -> set[str]:
    return {
        entity.unique_id
        for call in async_add_entities.call_args_list
        for entity in call.args[0]
    }


async def test_setup_adds_mower_sensors_only_for_gen1_mowers(
    hass, entry: MagicMock, coordinator: MagicMock, mower_device, mock_device: MagicMock
) -> None:
    coordinator.data = {mower_device.id: mower_device, "dev-2": mock_device}
    mock_device.id = "dev-2"
    entry.runtime_data = coordinator
    async_add_entities = MagicMock()

    await sensor.async_setup_entry(hass, entry, async_add_entities)

    added = _added_unique_ids(async_add_entities)
    assert {
        "dev-1_last_error",
        "dev-1_cutting_time",
        "dev-1_running_time",
        "dev-1_charging_cycles",
        "dev-1_collisions",
        "dev-1_battery",
    } <= added
    assert not {
        uid
        for uid in added
        if uid.startswith("dev-2_") and uid.endswith(("_last_error", "_cutting_time"))
    }
