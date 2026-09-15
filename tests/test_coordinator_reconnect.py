# SPDX-FileCopyrightText: 2026 GARDENA GmbH
#
# SPDX-License-Identifier: Apache-2.0

"""Tests for the GARDENA smart local coordinator's connection teardown."""

from __future__ import annotations

import asyncio
import contextlib
from unittest.mock import MagicMock, patch

import aiohttp
from homeassistant.core import HomeAssistant

from custom_components.gardena_smart_local_preview.coordinator import (
    GardenaSmartLocalCoordinator,
)


async def test_socket_teardown_drops_queued_frames(hass: HomeAssistant) -> None:
    """Frames queued for a closed socket are not replayed on the next connection."""
    coordinator = GardenaSmartLocalCoordinator(
        hass, "192.168.1.100", 8443, "testpassword"
    )
    coordinator._msg_queue.put_nowait('[{"op": "update"}]')
    session = MagicMock()
    session.ws_connect.side_effect = aiohttp.ClientConnectionError("gone")

    with patch(
        "custom_components.gardena_smart_local_preview.coordinator.async_get_clientsession",
        return_value=session,
    ):
        task = asyncio.get_running_loop().create_task(coordinator._ws_loop())
        # Let the loop fail its connect and run its teardown.
        for _ in range(10):
            await asyncio.sleep(0)
        assert session.ws_connect.called
        assert coordinator._msg_queue.empty()
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
