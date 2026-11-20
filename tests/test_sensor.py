# SPDX-FileCopyrightText: 2026 GARDENA GmbH
#
# SPDX-License-Identifier: Apache-2.0

"""Tests for the GARDENA smart local sensor platform."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock
from zoneinfo import ZoneInfo

from gardena_smart_local_api.devices import MowerNextStartSource
from homeassistant.util import dt as dt_util

from custom_components.gardena_smart_local_preview.sensor import (
    GardenaNextStartSensor,
    GardenaNextStartSourceSensor,
    GardenaTemperatureSensor,
)


def test_temperature_displayed_with_two_decimals(
    coordinator: MagicMock, mock_device: MagicMock
) -> None:
    """Gen2 reports float32 noise like 23.6429996490479, shown with two decimals."""
    mock_device.temperature = 23.6429996490479
    sensor = GardenaTemperatureSensor(coordinator, mock_device)

    assert sensor.native_value == 23.6429996490479
    assert sensor.suggested_display_precision == 2


def test_next_start_in_home_assistant_time_zone(
    coordinator: MagicMock, mock_device: MagicMock
) -> None:
    """The mower reports a naive local time, shown in Home Assistant's zone."""
    berlin = ZoneInfo("Europe/Berlin")
    dt_util.set_default_time_zone(berlin)
    mock_device.next_start = datetime(2026, 11, 20, 14, 6, 12)
    sensor = GardenaNextStartSensor(coordinator, mock_device)

    assert sensor.native_value == datetime(2026, 11, 20, 14, 6, 12, tzinfo=berlin)


def test_next_start_unknown_without_planned_start(
    coordinator: MagicMock, mock_device: MagicMock
) -> None:
    mock_device.next_start = None
    sensor = GardenaNextStartSensor(coordinator, mock_device)

    assert sensor.native_value is None


def test_next_start_source_is_one_of_its_options(
    coordinator: MagicMock, mock_device: MagicMock
) -> None:
    mock_device.next_start_source = MowerNextStartSource.CHARGING
    sensor = GardenaNextStartSourceSensor(coordinator, mock_device)

    assert sensor.native_value == "charging"
    assert sensor.native_value in sensor.options
