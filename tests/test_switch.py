# SPDX-FileCopyrightText: 2026 GARDENA GmbH
#
# SPDX-License-Identifier: Apache-2.0

"""Tests for the GARDENA smart local switch platform."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from homeassistant.const import EntityCategory

from custom_components.gardena_smart_local_preview.const import (
    CONF_POSITION_REPORTING,
)
from custom_components.gardena_smart_local_preview.switch import (
    GardenaPositionReportingSwitch,
)


@pytest.fixture
def position_reporting(
    coordinator: MagicMock, entry: MagicMock, mock_device: MagicMock
) -> GardenaPositionReportingSwitch:
    """Return a position reporting switch attached to a mocked hass."""
    entity = GardenaPositionReportingSwitch(coordinator, entry, mock_device)
    entity.hass = MagicMock()
    entity.async_write_ha_state = MagicMock()
    return entity


def test_position_reporting_is_off_without_subentry(
    position_reporting: GardenaPositionReportingSwitch,
) -> None:
    """Reporting is opt-in, and the switch stays available without a gateway."""
    assert position_reporting.is_on is False
    assert position_reporting.available is True
    assert position_reporting.unique_id == "dev-1_position_reporting"
    assert position_reporting.entity_category == EntityCategory.CONFIG


def test_position_reporting_reads_subentry(
    position_reporting: GardenaPositionReportingSwitch, subentry: MagicMock
) -> None:
    """A stored opt-in turns the switch on."""
    assert position_reporting.is_on is False
    subentry.data[CONF_POSITION_REPORTING] = True
    assert position_reporting.is_on is True


@pytest.mark.parametrize(
    ("method", "expected"), [("async_turn_on", True), ("async_turn_off", False)]
)
async def test_position_reporting_writes_subentry(
    position_reporting: GardenaPositionReportingSwitch,
    subentry: MagicMock,
    method: str,
    expected: bool,
) -> None:
    """Toggling stores the choice in the subentry, keeping the device id."""
    await getattr(position_reporting, method)()

    update_subentry = position_reporting.hass.config_entries.async_update_subentry
    update_subentry.assert_called_once()
    assert update_subentry.call_args.kwargs["data"] == {
        "device_id": "dev-1",
        CONF_POSITION_REPORTING: expected,
    }
    position_reporting.async_write_ha_state.assert_called_once()
