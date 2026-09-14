# SPDX-FileCopyrightText: 2026 GARDENA GmbH
#
# SPDX-License-Identifier: Apache-2.0

"""Tests for the GARDENA smart local integration setup."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir

from custom_components.gardena_smart_local_preview import (
    _async_exclude_and_report_failure,
)
from custom_components.gardena_smart_local_preview.const import DOMAIN


async def test_exclude_success_creates_no_issue(hass: HomeAssistant) -> None:
    """A confirmed exclusion does not warn the user."""
    coordinator = MagicMock()
    coordinator.async_exclude_device = AsyncMock(return_value=True)

    await _async_exclude_and_report_failure(hass, coordinator, "dev-1")

    coordinator.async_exclude_device.assert_awaited_once_with("dev-1")
    assert ir.async_get(hass).async_get_issue(DOMAIN, "exclude_failed_dev-1") is None


async def test_exclude_failure_creates_repair_issue(hass: HomeAssistant) -> None:
    """A gateway that does not confirm exclusion is surfaced to the user."""
    coordinator = MagicMock()
    coordinator.async_exclude_device = AsyncMock(return_value=False)

    await _async_exclude_and_report_failure(hass, coordinator, "dev-1")

    issue = ir.async_get(hass).async_get_issue(DOMAIN, "exclude_failed_dev-1")
    assert issue is not None
    assert issue.translation_key == "exclude_failed"
    assert issue.translation_placeholders == {"device_id": "dev-1"}


async def test_exclude_retry_success_clears_issue(hass: HomeAssistant) -> None:
    """Removing a still-paired device again resolves the earlier warning."""
    coordinator = MagicMock()
    coordinator.async_exclude_device = AsyncMock(return_value=False)
    await _async_exclude_and_report_failure(hass, coordinator, "dev-1")
    assert ir.async_get(hass).async_get_issue(DOMAIN, "exclude_failed_dev-1")

    coordinator.async_exclude_device = AsyncMock(return_value=True)
    await _async_exclude_and_report_failure(hass, coordinator, "dev-1")

    assert ir.async_get(hass).async_get_issue(DOMAIN, "exclude_failed_dev-1") is None
