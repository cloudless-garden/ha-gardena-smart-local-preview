# SPDX-FileCopyrightText: 2026 GARDENA GmbH
#
# SPDX-License-Identifier: Apache-2.0

"""Read-only helpers for Gen1 mower resources the library does not expose yet."""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta

from gardena_smart_local_api.devices import Gen1Mower1, Gen1Mower2
from gardena_smart_local_api.devices.device import Device
from gardena_smart_local_api.resources import IpsoPath

# Reported instead of an error name when there is nothing to report.
NO_MESSAGE = "no_message"

# Error code -> translation state. Left empty on purpose: the local codes are
# not confirmed to follow any published numbering, so entries are only added
# after being matched against the cloud integration's error text (see
# docs/automation-kalibracja.yaml). Unknown codes are exposed as "code_<n>".
ERROR_CODES: dict[int, str] = {}

# Codes that do not describe a fault (0 = no error since the last reset).
INFORMATIONAL_CODES: frozenset[int] = frozenset({0})

_UTC_OFFSET_RE = re.compile(
    r"^UTC(?:(?P<sign>[+-])(?P<hours>\d{2}):(?P<minutes>\d{2}))?$"
)


def is_gen1_mower(device: object) -> bool:
    return isinstance(device, (Gen1Mower1, Gen1Mower2))


def _lemonbeat_path(resource_name: str) -> IpsoPath:
    return IpsoPath(
        object_name="lemonbeat", object_instance_id="0", resource_name=resource_name
    )


def get_lemonbeat_int(device: Device, resource_name: str) -> int | None:
    value = device.get_value(_lemonbeat_path(resource_name))
    return value if isinstance(value, int) else None


def get_last_error_code(device: Device) -> int | None:
    return get_lemonbeat_int(device, "last_error_code")


def parse_utc_offset(text: str | None) -> timedelta | None:
    """Parse the gateway's ``utc_offset`` string, e.g. ``UTC+02:00``."""
    if not isinstance(text, str):
        return None
    match = _UTC_OFFSET_RE.match(text)
    if match is None:
        return None
    if match.group("sign") is None:
        return timedelta(0)
    offset = timedelta(
        hours=int(match.group("hours")), minutes=int(match.group("minutes"))
    )
    return -offset if match.group("sign") == "-" else offset


def get_utc_offset(device: Device) -> timedelta:
    value = device.get_value(
        IpsoPath(
            object_name="device", object_instance_id="0", resource_name="utc_offset"
        )
    )
    return parse_utc_offset(value if isinstance(value, str) else None) or timedelta(0)


def _get_local_epoch(device: Device, resource_name: str) -> datetime | None:
    # The mower reports these as 4 bytes big-endian "seconds since 1970 in
    # local time", i.e. already shifted by the device's UTC offset. Undo the
    # shift so Home Assistant gets a real instant.
    value = device.get_value(_lemonbeat_path(resource_name))
    if not isinstance(value, bytes) or len(value) != 4:
        return None
    seconds = int.from_bytes(value, "big")
    if seconds == 0:
        return None
    return datetime.fromtimestamp(seconds, UTC) - get_utc_offset(device)


def get_last_error_timestamp(device: Device) -> datetime | None:
    return _get_local_epoch(device, "timestamp_last_error_code")


def error_code_to_state(code: int | None) -> str | None:
    if code is None:
        return None
    if code in INFORMATIONAL_CODES:
        return NO_MESSAGE
    return ERROR_CODES.get(code, f"code_{code}")


def get_current_error_codes(device: Device) -> list[int]:
    """Currently active error codes; 0 is the gateway's "no error" marker."""
    value = device.get_value(
        IpsoPath(
            object_name="device", object_instance_id="0", resource_name="error_code"
        )
    )
    if not isinstance(value, list):
        return []
    return [code for code in value if isinstance(code, int) and code != 0]
