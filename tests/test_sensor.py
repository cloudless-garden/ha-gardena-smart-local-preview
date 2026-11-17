# SPDX-FileCopyrightText: 2026 GARDENA GmbH
#
# SPDX-License-Identifier: Apache-2.0

"""Tests for the GARDENA smart local sensor platform."""

from __future__ import annotations

from unittest.mock import MagicMock

from custom_components.gardena_smart_local_preview.sensor import (
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
