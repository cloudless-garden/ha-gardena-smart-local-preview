# SPDX-FileCopyrightText: 2026 GARDENA GmbH
#
# SPDX-License-Identifier: Apache-2.0

"""Tests for the GARDENA smart local number platform."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from homeassistant.const import UnitOfTime

from custom_components.gardena_smart_local_preview.const import (
    CONF_MOWER_DURATION,
    DEFAULT_MOWER_DURATION_HOURS,
)
from custom_components.gardena_smart_local_preview.number import GardenaMowerDuration


@pytest.fixture
def mower_duration(
    coordinator: MagicMock, entry: MagicMock, mock_device: MagicMock
) -> GardenaMowerDuration:
    """Return a mower duration entity attached to a mocked hass."""
    entity = GardenaMowerDuration(coordinator, entry, mock_device)
    entity.hass = MagicMock()
    entity.async_write_ha_state = MagicMock()
    return entity


def test_mower_duration_defaults_without_subentry(
    mower_duration: GardenaMowerDuration,
) -> None:
    """Without a subentry the entity reports the default and stays available."""
    assert mower_duration.available is True
    assert mower_duration.native_value == DEFAULT_MOWER_DURATION_HOURS
    assert mower_duration.native_unit_of_measurement == UnitOfTime.HOURS
    assert mower_duration.unique_id == "dev-1_mower_duration"
    assert mower_duration.name == "Default Mowing Duration"


def test_mower_duration_range(mower_duration: GardenaMowerDuration) -> None:
    """The duration can be set from 1 to 6 hours."""
    assert mower_duration.native_min_value == 1
    assert mower_duration.native_max_value == 6


def test_mower_duration_reads_configured_hours(
    mower_duration: GardenaMowerDuration, subentry: MagicMock
) -> None:
    """A stored hour count is reported as the value."""
    subentry.data[CONF_MOWER_DURATION] = 3

    assert mower_duration.native_value == 3


async def test_mower_duration_set_writes_hours_to_subentry(
    mower_duration: GardenaMowerDuration, subentry: MagicMock
) -> None:
    """Setting a value persists the hour count."""
    await mower_duration.async_set_native_value(2.0)

    update_subentry = mower_duration.hass.config_entries.async_update_subentry
    update_subentry.assert_called_once()
    _, kwargs = update_subentry.call_args
    assert kwargs["data"][CONF_MOWER_DURATION] == 2
    mower_duration.async_write_ha_state.assert_called_once()


async def test_mower_duration_set_without_subentry_is_noop(
    mower_duration: GardenaMowerDuration,
) -> None:
    """Without a subentry there is nowhere to store the value, so nothing happens."""
    await mower_duration.async_set_native_value(2.0)

    mower_duration.hass.config_entries.async_update_subentry.assert_not_called()
