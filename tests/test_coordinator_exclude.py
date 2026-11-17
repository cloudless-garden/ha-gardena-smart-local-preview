# SPDX-FileCopyrightText: 2026 GARDENA GmbH
#
# SPDX-License-Identifier: Apache-2.0

"""Tests for the GARDENA smart local coordinator's device exclusion."""

from __future__ import annotations

import pytest
from homeassistant.core import HomeAssistant

from custom_components.gardena_smart_local_preview.coordinator import (
    GardenaSmartLocalCoordinator,
)


@pytest.fixture
def coordinator(hass: HomeAssistant) -> GardenaSmartLocalCoordinator:
    """Return a coordinator that is not connected to a gateway."""
    return GardenaSmartLocalCoordinator(hass, "192.168.1.100", 8443, "testpassword")


async def test_exclude_already_absent_device_succeeds(
    coordinator: GardenaSmartLocalCoordinator,
) -> None:
    """Excluding a device already gone from the map counts as success.

    A delete event or a fresh discovery can remove it first (e.g. it was
    excluded through the official app); there is nothing left to reject,
    so this must not report a failure that creates a misleading repair
    issue.
    """
    assert await coordinator.async_exclude_device("dev-1") is True
