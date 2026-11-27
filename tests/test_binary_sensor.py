# SPDX-FileCopyrightText: 2026 GARDENA GmbH
#
# SPDX-License-Identifier: Apache-2.0

"""Tests for the GARDENA smart local binary sensor platform."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from gardena_smart_local_api.devices import MowerState
from homeassistant.components.binary_sensor import BinarySensorDeviceClass

from custom_components.gardena_smart_local_preview import binary_sensor
from custom_components.gardena_smart_local_preview.binary_sensor import (
    GardenaMowerProblemSensor,
)


def test_problem_sensor_metadata(
    coordinator: MagicMock, mock_device: MagicMock
) -> None:
    sensor = GardenaMowerProblemSensor(coordinator, mock_device)

    assert sensor.unique_id == "dev-1_problem"
    assert sensor.device_class == BinarySensorDeviceClass.PROBLEM


@pytest.mark.parametrize(
    ("state", "expected"),
    [
        (MowerState.ERROR, True),
        (MowerState.MOWING, False),
        (MowerState.PARKED, False),
        (MowerState.UNKNOWN, None),
    ],
)
def test_problem_sensor_follows_mower_error_state(
    coordinator: MagicMock,
    mock_device: MagicMock,
    state: MowerState,
    expected: bool | None,
) -> None:
    mock_device.state = state
    sensor = GardenaMowerProblemSensor(coordinator, mock_device)

    assert sensor.is_on is expected


def test_problem_sensor_is_unknown_without_device(
    coordinator: MagicMock, mock_device: MagicMock
) -> None:
    sensor = GardenaMowerProblemSensor(coordinator, mock_device)
    coordinator.data = {}

    assert sensor.is_on is None


async def test_problem_sensor_is_added_only_for_mowers(
    hass, entry: MagicMock, coordinator: MagicMock, mock_device: MagicMock
) -> None:
    # spec_set leaves out build_start_mowing_obj, so this is not a mower
    other_device = MagicMock(spec_set=["id"])
    other_device.id = "dev-2"
    coordinator.data = {mock_device.id: mock_device, other_device.id: other_device}
    entry.runtime_data = coordinator
    async_add_entities = MagicMock()

    await binary_sensor.async_setup_entry(hass, entry, async_add_entities)

    added = [e for call in async_add_entities.call_args_list for e in call.args[0]]
    problem = [e for e in added if isinstance(e, GardenaMowerProblemSensor)]
    assert [e.unique_id for e in problem] == ["dev-1_problem"]
