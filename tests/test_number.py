# SPDX-FileCopyrightText: 2026 GARDENA GmbH
#
# SPDX-License-Identifier: Apache-2.0

"""Tests for the GARDENA smart local number platform."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.const import UnitOfTime

from custom_components.gardena_smart_local_preview.const import (
    CONF_MOWER_DURATION,
    DEFAULT_MOWER_DURATION_HOURS,
)
from custom_components.gardena_smart_local_preview.number import GardenaMowerDuration


def _mock_device():
    device = MagicMock()
    device.id = "dev-1"
    device.serial_number = "00000001"
    device.software_version = "1.0.0"
    device.hardware_version = "1.0"
    device.model_definition.name = "Smart SILENO"
    device.model_definition.model_number = "1"
    device.valve_ids = []
    return device


@pytest.fixture
def coordinator() -> MagicMock:
    coord = MagicMock()
    coord.connected = True
    coord.send_request = AsyncMock(return_value=[])
    return coord


def _entry(subentries: dict | None = None) -> MagicMock:
    cfg = MagicMock()
    cfg.subentries = subentries or {}
    return cfg


def _build(coordinator: MagicMock, entry: MagicMock) -> GardenaMowerDuration:
    device = _mock_device()
    coordinator.data = {device.id: device}
    entity = GardenaMowerDuration(coordinator, entry, device)
    entity.hass = MagicMock()
    entity.async_write_ha_state = MagicMock()
    return entity


def test_mower_duration_defaults_without_subentry(coordinator: MagicMock) -> None:
    """Without a subentry the entity reports the default and stays available."""
    entity = _build(coordinator, _entry())

    assert entity.available is True
    assert entity.native_value == DEFAULT_MOWER_DURATION_HOURS
    assert entity.native_unit_of_measurement == UnitOfTime.HOURS
    assert entity.unique_id == "dev-1_mower_duration"
    assert entity.name == "Default Mowing Duration"


def test_mower_duration_range(coordinator: MagicMock) -> None:
    """The duration can be set from 1 to 6 hours."""
    entity = _build(coordinator, _entry())

    assert entity.native_min_value == 1
    assert entity.native_max_value == 6


def test_mower_duration_reads_configured_hours(coordinator: MagicMock) -> None:
    """A stored hour count is reported as the value."""
    subentry = MagicMock()
    subentry.data = {"device_id": "dev-1", CONF_MOWER_DURATION: 3}
    entity = _build(coordinator, _entry({"sub-1": subentry}))

    assert entity.native_value == 3


async def test_mower_duration_set_writes_hours_to_subentry(
    coordinator: MagicMock,
) -> None:
    """Setting a value persists the hour count."""
    subentry = MagicMock()
    subentry.data = {"device_id": "dev-1"}
    entity = _build(coordinator, _entry({"sub-1": subentry}))

    await entity.async_set_native_value(2.0)

    entity.hass.config_entries.async_update_subentry.assert_called_once()
    _, kwargs = entity.hass.config_entries.async_update_subentry.call_args
    assert kwargs["data"][CONF_MOWER_DURATION] == 2
    entity.async_write_ha_state.assert_called_once()


async def test_mower_duration_set_without_subentry_is_noop(
    coordinator: MagicMock,
) -> None:
    """Without a subentry there is nowhere to store the value, so nothing happens."""
    entity = _build(coordinator, _entry())

    await entity.async_set_native_value(2.0)

    entity.hass.config_entries.async_update_subentry.assert_not_called()
