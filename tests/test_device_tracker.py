# SPDX-FileCopyrightText: 2026 GARDENA GmbH
#
# SPDX-License-Identifier: Apache-2.0

"""Tests for the mower position device tracker."""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import MagicMock

import pytest
from gardena_smart_local_api.devices import Gen1Mower1
from gardena_smart_local_api.model_loader import Gen1ModelDefinition
from homeassistant.components.device_tracker import SourceType
from homeassistant.const import Platform
from homeassistant.exceptions import HomeAssistantError
from homeassistant.util import dt as dt_util

from custom_components.gardena_smart_local_preview import PLATFORMS, device_tracker
from custom_components.gardena_smart_local_preview.const import (
    CONF_POSITION_REPORTING,
)
from custom_components.gardena_smart_local_preview.device_tracker import (
    POSITION_REPORTING_RENEWAL,
    POSITION_REPORTING_TIMEOUT,
    GardenaMowerTracker,
)
from tests.common import POSITION_B64, make_gen1_mower


@pytest.fixture
def entry() -> MagicMock:
    """Return a config entry whose mower subentry has position reporting on."""
    cfg = MagicMock()
    sub = MagicMock()
    sub.data = {"device_id": "dev-1", CONF_POSITION_REPORTING: True}
    cfg.subentries = {"sub-1": sub}
    return cfg


def _tracker(
    coordinator: MagicMock, entry: MagicMock, lemonbeat: dict
) -> GardenaMowerTracker:
    device = make_gen1_mower(lemonbeat)
    coordinator.data = {device.id: device}
    return GardenaMowerTracker(coordinator, entry, device)


def _sent_position_timer(coordinator: MagicMock) -> int:
    """Return the position_timer value of the single request sent."""
    coordinator.send_request.assert_awaited_once()
    request = coordinator.send_request.await_args.args[1].root[0]
    assert str(request.entity.path) == "lemonbeat/0/position_timer"
    return request.payload["vi"]


def test_device_tracker_platform_is_loaded() -> None:
    assert Platform.DEVICE_TRACKER in PLATFORMS


def test_tracker_metadata(coordinator: MagicMock, entry: MagicMock) -> None:
    tracker = _tracker(coordinator, entry, {})

    assert tracker.unique_id == "dev-1_position"
    assert tracker.translation_key == "position"
    assert tracker.source_type == SourceType.GPS


def test_tracker_reports_lona_position(
    coordinator: MagicMock, entry: MagicMock
) -> None:
    tracker = _tracker(coordinator, entry, {"position": {"vo": POSITION_B64}})

    assert tracker.latitude == pytest.approx(47.3637)
    assert tracker.longitude == pytest.approx(8.5127)
    # Raw GNSS accuracy 2500 is taken as millimetres
    assert tracker.location_accuracy == pytest.approx(2.5)
    attributes = tracker.extra_state_attributes
    assert attributes["heading"] == pytest.approx(224.8)
    assert attributes["lona_is_ready"] is True
    assert attributes["gnss_horizontal_accuracy"] == 2500
    assert attributes["compass_is_calibrated"] is True
    assert "latitude" not in attributes
    assert "longitude" not in attributes


def test_tracker_without_position_is_unknown(
    coordinator: MagicMock, entry: MagicMock
) -> None:
    tracker = _tracker(coordinator, entry, {"position": {"vo": ""}})

    assert tracker.latitude is None
    assert tracker.longitude is None
    assert tracker.location_accuracy == 0
    assert tracker.extra_state_attributes == {}


@pytest.mark.parametrize(
    ("status", "requested_ago", "expected"),
    [
        (1, None, True),  # OK_CUTTING_AUTO, never requested
        (4, None, True),  # OK_LEAVING_CS
        (2, None, True),  # OK_SEARCHING_CS
        (8, None, False),  # PARKED_BY_USER
        (3, None, False),  # OK_CHARGING
        (None, None, False),  # unknown state
        (1, timedelta(minutes=10), False),  # still covered by the last request
        (1, timedelta(minutes=51), True),  # renewal window reached
    ],
)
def test_position_reporting_is_due_only_while_active(
    coordinator: MagicMock,
    entry: MagicMock,
    status: int | None,
    requested_ago: timedelta | None,
    expected: bool,
) -> None:
    lemonbeat = {"status": {"vi": status}} if status is not None else {}
    tracker = _tracker(coordinator, entry, lemonbeat)
    now = dt_util.utcnow()
    if requested_ago is not None:
        tracker._reporting_requested_at = now - requested_ago

    assert tracker.position_reporting_due(now) is expected


@pytest.mark.parametrize("stored", [False, None])
def test_position_reporting_is_never_due_unless_opted_in(
    coordinator: MagicMock, entry: MagicMock, stored: bool | None
) -> None:
    data = entry.subentries["sub-1"].data
    if stored is None:
        del data[CONF_POSITION_REPORTING]
    else:
        data[CONF_POSITION_REPORTING] = stored
    tracker = _tracker(coordinator, entry, {"status": {"vi": 1}})

    assert tracker.position_reporting_due(dt_util.utcnow()) is False


def test_coordinator_update_sends_nothing_unless_opted_in(
    coordinator: MagicMock, entry: MagicMock
) -> None:
    entry.subentries["sub-1"].data[CONF_POSITION_REPORTING] = False
    tracker = _tracker(coordinator, entry, {"status": {"vi": 1}})
    tracker.hass = MagicMock()
    tracker.async_write_ha_state = MagicMock()

    tracker._handle_coordinator_update()

    entry.async_create_background_task.assert_not_called()
    coordinator.send_request.assert_not_called()


def test_renewal_happens_before_the_gateway_timeout() -> None:
    assert POSITION_REPORTING_RENEWAL < timedelta(seconds=POSITION_REPORTING_TIMEOUT)
    assert POSITION_REPORTING_TIMEOUT == 3600


async def test_send_position_reporting_writes_position_timer(
    coordinator: MagicMock, entry: MagicMock
) -> None:
    tracker = _tracker(coordinator, entry, {})

    assert await tracker.async_send_position_reporting(3600) is True
    assert _sent_position_timer(coordinator) == 3600


async def test_send_position_reporting_failure_is_reported_not_raised(
    coordinator: MagicMock, entry: MagicMock
) -> None:
    tracker = _tracker(coordinator, entry, {})
    coordinator.send_request.side_effect = HomeAssistantError("rejected")

    assert await tracker.async_send_position_reporting(3600) is False


async def test_schedule_position_reporting_runs_as_entry_background_task(
    coordinator: MagicMock, entry: MagicMock
) -> None:
    tracker = _tracker(coordinator, entry, {"status": {"vi": 1}})
    tracker.hass = MagicMock()

    tracker.schedule_position_reporting()

    # The entry owns the task, so unloading the entry cancels it
    entry.async_create_background_task.assert_called_once()
    hass, coro, name = entry.async_create_background_task.call_args.args
    assert hass is tracker.hass
    assert name == "gardena_position_reporting_dev-1"
    assert tracker._reporting_requested_at is not None
    await coro
    assert _sent_position_timer(coordinator) == POSITION_REPORTING_TIMEOUT


async def test_schedule_position_reporting_retries_after_failure(
    coordinator: MagicMock, entry: MagicMock
) -> None:
    tracker = _tracker(coordinator, entry, {"status": {"vi": 1}})
    tracker.hass = MagicMock()
    coordinator.send_request.side_effect = HomeAssistantError("rejected")

    tracker.schedule_position_reporting()
    await entry.async_create_background_task.call_args.args[1]

    assert tracker._reporting_requested_at is None


async def test_added_to_hass_sends_nothing(
    hass, coordinator: MagicMock, entry: MagicMock
) -> None:
    tracker = _tracker(coordinator, entry, {"status": {"vi": 8}})
    tracker.hass = hass

    await tracker.async_added_to_hass()
    await hass.async_block_till_done()

    coordinator.send_request.assert_not_awaited()


async def test_setup_adds_tracker_only_for_position_capable_mowers(
    hass, entry: MagicMock, coordinator: MagicMock
) -> None:
    lona = make_gen1_mower()
    plain = Gen1Mower1(
        id="dev-2",
        data=lona.data,
        model_definition=Gen1ModelDefinition(model_number="29694", name="Plain"),
    )
    coordinator.data = {lona.id: lona, plain.id: plain}
    entry.runtime_data = coordinator
    async_add_entities = MagicMock()

    await device_tracker.async_setup_entry(hass, entry, async_add_entities)

    added = [e for call in async_add_entities.call_args_list for e in call.args[0]]
    assert [e.unique_id for e in added] == ["dev-1_position"]
