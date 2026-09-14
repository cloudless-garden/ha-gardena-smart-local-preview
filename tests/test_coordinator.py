# SPDX-FileCopyrightText: 2026 GARDENA GmbH
#
# SPDX-License-Identifier: Apache-2.0

"""Tests for the GARDENA smart local coordinator's unknown-device rediscovery."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.core import HomeAssistant

from custom_components.gardena_smart_local_preview.coordinator import (
    GardenaSmartLocalCoordinator,
)


@pytest.fixture
def coordinator(hass: HomeAssistant) -> GardenaSmartLocalCoordinator:
    """Return a coordinator that is not connected to a gateway."""
    return GardenaSmartLocalCoordinator(hass, "192.168.1.100", 8443, "testpassword")


def test_schedule_unknown_device_discovery_reschedules_on_burst(
    coordinator: GardenaSmartLocalCoordinator,
) -> None:
    """A burst of events collapses into a single pending re-discovery."""
    first_handle = MagicMock()
    second_handle = MagicMock()
    coordinator.hass.loop.call_later = MagicMock(
        side_effect=[first_handle, second_handle]
    )

    coordinator._schedule_unknown_device_discovery("dev-1")
    coordinator._schedule_unknown_device_discovery("dev-2")

    first_handle.cancel.assert_called_once()
    second_handle.cancel.assert_not_called()
    assert coordinator._unknown_device_discovery_handle is second_handle


async def test_discover_unknown_devices_runs_full_discovery(
    coordinator: GardenaSmartLocalCoordinator,
) -> None:
    """The debounced run re-discovers and clears its handle.

    The handle here stands for "a run is scheduled" (see
    _schedule_unknown_device_discovery). By the time this runs, the real
    timer has already elapsed, so the handle is just a stale reference to
    clear, not something to cancel; a MagicMock stands in for it.
    """
    coordinator._unknown_device_discovery_handle = MagicMock()
    coordinator._do_discovery = AsyncMock()

    await coordinator._discover_unknown_devices()

    coordinator._do_discovery.assert_awaited_once()
    assert coordinator._unknown_device_discovery_handle is None


async def test_discover_unknown_devices_failure_clears_handle(
    coordinator: GardenaSmartLocalCoordinator,
) -> None:
    """A failed re-discovery still clears the handle, so a later event can retry."""
    coordinator._unknown_device_discovery_handle = MagicMock()
    coordinator._do_discovery = AsyncMock(side_effect=RuntimeError("boom"))

    await coordinator._discover_unknown_devices()

    assert coordinator._unknown_device_discovery_handle is None


async def test_async_disconnect_cancels_pending_rediscovery(
    coordinator: GardenaSmartLocalCoordinator,
) -> None:
    """Disconnecting cancels a still-pending re-discovery timer."""
    handle = coordinator.hass.loop.call_later(99, lambda: None)
    coordinator._unknown_device_discovery_handle = handle

    await coordinator.async_disconnect()

    assert coordinator._unknown_device_discovery_handle is None
