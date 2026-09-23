# SPDX-FileCopyrightText: 2026 GARDENA GmbH
#
# SPDX-License-Identifier: Apache-2.0

"""Tests for the Gen1 mower resource helpers."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

import pytest

from custom_components.gardena_smart_local_preview import mower
from tests.common import make_gen1_mower as make_mower


def test_is_gen1_mower_only_for_lemonbeat_mowers() -> None:
    assert mower.is_gen1_mower(make_mower()) is True
    assert mower.is_gen1_mower(MagicMock()) is False


def test_last_error_code_reads_lemonbeat_value() -> None:
    device = make_mower({"last_error_code": {"vi": 15}})

    assert mower.get_last_error_code(device) == 15


def test_last_error_code_is_none_when_not_reported() -> None:
    assert mower.get_last_error_code(make_mower()) is None


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("UTC+02:00", timedelta(hours=2)),
        ("UTC-05:30", timedelta(hours=-5, minutes=-30)),
        ("UTC", timedelta(0)),
        ("garbage", None),
        (None, None),
    ],
)
def test_parse_utc_offset(text: str | None, expected: timedelta | None) -> None:
    assert mower.parse_utc_offset(text) == expected


def test_last_error_timestamp_is_local_epoch_shifted_by_utc_offset() -> None:
    # 0x6ab3c0de = 1790165214 = 2026-09-23 12:06:54 "local time as UTC"
    device = make_mower({"timestamp_last_error_code": {"vo": "arPA3g=="}})

    assert mower.get_last_error_timestamp(device) == datetime(
        2026, 9, 23, 10, 6, 54, tzinfo=UTC
    )


def test_last_error_timestamp_treats_unknown_offset_as_utc() -> None:
    device = make_mower(
        {"timestamp_last_error_code": {"vo": "arPA3g=="}},
        {"utc_offset": {"vs": "garbage"}},
    )

    assert mower.get_last_error_timestamp(device) == datetime(
        2026, 9, 23, 12, 6, 54, tzinfo=UTC
    )


@pytest.mark.parametrize(
    "lemonbeat",
    [
        {},
        {"timestamp_last_error_code": {"vo": "AAAAAA=="}},  # 0 = never
        {"timestamp_last_error_code": {"vo": "AAA="}},  # truncated
    ],
)
def test_last_error_timestamp_is_none_when_missing_or_zero(lemonbeat: dict) -> None:
    assert mower.get_last_error_timestamp(make_mower(lemonbeat)) is None


def test_error_code_to_state_without_table_exposes_raw_code() -> None:
    assert mower.error_code_to_state(None) is None
    assert mower.error_code_to_state(0) == mower.NO_MESSAGE
    assert mower.error_code_to_state(15) == "code_15"


def test_error_code_to_state_uses_calibrated_table(monkeypatch) -> None:
    monkeypatch.setitem(mower.ERROR_CODES, 15, "lifted")

    assert mower.error_code_to_state(15) == "lifted"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ({"error_code": {"ai": [0]}}, []),
        ({"error_code": {"ai": [15]}}, [15]),
        ({"error_code": {"ai": [15, 0, 3]}}, [15, 3]),
        ({"error_code": {"ai": None}}, []),
    ],
)
def test_current_error_codes_drop_the_no_error_marker(
    raw: dict, expected: list[int]
) -> None:
    assert mower.get_current_error_codes(make_mower(device=raw)) == expected


def test_current_error_codes_empty_when_not_reported() -> None:
    device = make_mower()
    del device.data["device"]["0"]["error_code"]

    assert mower.get_current_error_codes(device) == []


@pytest.mark.parametrize(
    ("resource", "value"),
    [
        ("cutting_time", 1269),
        ("running_time", 1345),
        ("charging_cycles", 933),
        ("collisions", 3120),
    ],
)
def test_statistics_read_lemonbeat_ints(resource: str, value: int) -> None:
    device = make_mower({resource: {"vi": value}})

    assert mower.get_lemonbeat_int(device, resource) == value
    assert mower.get_lemonbeat_int(make_mower(), resource) is None
