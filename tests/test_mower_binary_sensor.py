# SPDX-FileCopyrightText: 2026 GARDENA GmbH
#
# SPDX-License-Identifier: Apache-2.0

"""Tests for the mower problem binary sensor."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from homeassistant.components.binary_sensor import BinarySensorDeviceClass

from custom_components.gardena_smart_local_preview import binary_sensor
from custom_components.gardena_smart_local_preview.binary_sensor import (
    GardenaMowerProblemSensor,
)
from tests.common import make_gen1_mower


def _entity(coordinator: MagicMock, status: int | None, error_codes: list[int]):
    lemonbeat = {"status": {"vi": status}} if status is not None else {}
    device = make_gen1_mower(lemonbeat, {"error_code": {"ai": error_codes}})
    coordinator.data = {device.id: device}
    return GardenaMowerProblemSensor(coordinator, device)


def test_problem_sensor_metadata(coordinator: MagicMock) -> None:
    entity = _entity(coordinator, 4, [0])

    assert entity.unique_id == "dev-1_problem"
    assert entity.translation_key == "problem"
    assert entity.device_class == BinarySensorDeviceClass.PROBLEM


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        (12, True),  # ERROR
        (13, True),  # ERROR_POWER_UP
        (4, False),  # OK_LEAVING_CS
        (8, False),  # PARKED_BY_USER
        (None, None),  # not reported yet
    ],
)
def test_problem_sensor_follows_mower_error_state(
    coordinator: MagicMock, status: int | None, expected: bool | None
) -> None:
    entity = _entity(coordinator, status, [0])

    assert entity.is_on is expected


def test_problem_sensor_lists_active_error_codes(coordinator: MagicMock) -> None:
    entity = _entity(coordinator, 12, [15])

    assert entity.extra_state_attributes == {"error_codes": [15]}


def test_problem_sensor_has_no_codes_when_healthy(coordinator: MagicMock) -> None:
    entity = _entity(coordinator, 4, [0])

    assert entity.extra_state_attributes == {"error_codes": []}


async def test_setup_adds_problem_sensor_for_mowers(
    hass, entry: MagicMock, coordinator: MagicMock
) -> None:
    device = make_gen1_mower({"status": {"vi": 4}})
    coordinator.data = {device.id: device}
    entry.runtime_data = coordinator
    async_add_entities = MagicMock()

    await binary_sensor.async_setup_entry(hass, entry, async_add_entities)

    added = [e for call in async_add_entities.call_args_list for e in call.args[0]]
    assert [e.unique_id for e in added] == ["dev-1_problem"]
