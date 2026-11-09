# SPDX-FileCopyrightText: 2026 GARDENA GmbH
#
# SPDX-License-Identifier: Apache-2.0

"""Shared test helpers."""

from __future__ import annotations

from gardena_smart_local_api.devices import Gen1Mower2
from gardena_smart_local_api.model_loader import Gen1ModelDefinition

# Raw 26-byte LONA position from the library's fixture: 47.3637, 8.5127,
# GNSS accuracy 2500, heading 224.8°, LONA ready, compass calibrated.
POSITION_B64 = "HDscoAUS63AAAAnEHDsgiAUS71gIyAEIygE="


def make_gen1_mower(
    lemonbeat: dict | None = None, device: dict | None = None
) -> Gen1Mower2:
    """Build a real Gen1 LONA mower from raw gateway resources."""
    data = {
        "connection_status": {"0": {"online": {"vb": True}}},
        "device": {
            "0": {
                "serial_number": {"vs": "202200000000"},
                "software_version": {"vs": "2.6.0"},
                "hardware_version": {"vs": "1.0.0"},
                "utc_offset": {"vs": "UTC+02:00"},
                "error_code": {"ai": [0]},
                **(device or {}),
            }
        },
        "lemonbeat": {"0": lemonbeat or {}},
    }
    return Gen1Mower2(
        id="dev-1",
        data=data,
        model_definition=Gen1ModelDefinition(
            model_number="53988", name="smart SILENO city/life (with LONA)"
        ),
    )
