# SPDX-FileCopyrightText: 2026 GARDENA GmbH
#
# SPDX-License-Identifier: Apache-2.0

"""Tests for the GARDENA smart local coordinator's ErrorMessage handling."""

from __future__ import annotations

import asyncio
import contextlib

import pytest
from gardena_smart_local_api.messages import (
    ErrorMessage,
    ErrorMetadata,
    IngressMessageList,
)
from homeassistant.core import HomeAssistant

from custom_components.gardena_smart_local_preview.coordinator import (
    GardenaSmartLocalCoordinator,
)


@pytest.fixture
def coordinator(hass: HomeAssistant) -> GardenaSmartLocalCoordinator:
    """Return a coordinator that is not connected to a gateway."""
    return GardenaSmartLocalCoordinator(hass, "192.168.1.100", 8443, "testpassword")


async def test_msg_consumer_resolves_pending_reply_on_error_message(
    coordinator: GardenaSmartLocalCoordinator,
) -> None:
    """A gateway ErrorMessage resolves the matching pending future.

    Only Reply used to be matched against _pending_replies; an
    ErrorMessage fell through to the generic event handler, which
    silently drops it, so a rejected command just timed out instead of
    surfacing the actual rejection.
    """
    loop = asyncio.get_running_loop()
    fut = loop.create_future()
    coordinator._pending_replies["req-1"] = fut

    error = ErrorMessage(
        metadata=ErrorMetadata(error_source="test"),
        request_id="req-1",
        success=False,
        payload={"vs": "not allowed"},
    )
    coordinator._msg_queue.put_nowait(IngressMessageList([error]).model_dump_json())

    task = loop.create_task(coordinator._msg_consumer())
    try:
        result = await asyncio.wait_for(fut, timeout=1)
    finally:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task

    assert result == error
    assert "req-1" not in coordinator._pending_replies
