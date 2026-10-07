# SPDX-FileCopyrightText: 2026 GARDENA GmbH
#
# SPDX-License-Identifier: Apache-2.0

"""Tests for the GARDENA smart local integration setup."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_PORT
from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.gardena_smart_local_preview import (
    _async_exclude_and_report_failure,
    _async_migrate_unique_id,
)
from custom_components.gardena_smart_local_preview.const import DOMAIN

PATCH_EXTRACT_HOSTNAME = (
    "custom_components.gardena_smart_local_preview.config_flow"
    ".async_extract_hostname_from_cert"
)


def _add_entry(hass: HomeAssistant, host: str, unique_id: str) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=unique_id,
        data={CONF_HOST: host, CONF_PORT: 8443, CONF_PASSWORD: ""},
    )
    entry.add_to_hass(hass)
    return entry


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


async def test_migrate_unique_id_replaces_host(hass: HomeAssistant) -> None:
    """An entry identified by its host moves to the gateway name."""
    entry = _add_entry(hass, "192.168.1.10", "192.168.1.10")

    with patch(PATCH_EXTRACT_HOSTNAME, return_value="GARDENA-123456"):
        await _async_migrate_unique_id(hass, entry)

    assert entry.unique_id == "GARDENA-123456"


async def test_migrate_unique_id_keeps_host_without_hostname(
    hass: HomeAssistant,
) -> None:
    """A gateway whose certificate has no name keeps the host as unique_id."""
    entry = _add_entry(hass, "192.168.1.10", "192.168.1.10")

    with patch(PATCH_EXTRACT_HOSTNAME, return_value=None):
        await _async_migrate_unique_id(hass, entry)

    assert entry.unique_id == "192.168.1.10"


async def test_migrate_unique_id_is_idempotent(hass: HomeAssistant) -> None:
    """An entry that already has the gateway name is left alone."""
    entry = _add_entry(hass, "192.168.1.10", "GARDENA-123456")

    with (
        patch(PATCH_EXTRACT_HOSTNAME, return_value="GARDENA-123456"),
        patch.object(hass.config_entries, "async_update_entry") as update_entry,
    ):
        await _async_migrate_unique_id(hass, entry)

    update_entry.assert_not_called()


async def test_migrate_unique_id_duplicate_creates_repair_issue(
    hass: HomeAssistant,
) -> None:
    """A second entry for the same gateway is reported instead of renamed."""
    _add_entry(hass, "192.168.1.10", "GARDENA-123456")
    duplicate = _add_entry(hass, "192.168.1.11", "192.168.1.11")

    with patch(PATCH_EXTRACT_HOSTNAME, return_value="GARDENA-123456"):
        await _async_migrate_unique_id(hass, duplicate)

    assert duplicate.unique_id == "192.168.1.11"
    issue = ir.async_get(hass).async_get_issue(
        DOMAIN, f"duplicate_gateway_{duplicate.entry_id}"
    )
    assert issue is not None
    assert issue.translation_key == "duplicate_gateway"
    assert issue.translation_placeholders == {"hostname": "GARDENA-123456"}


async def test_migrate_unique_id_clears_resolved_duplicate_issue(
    hass: HomeAssistant,
) -> None:
    """Removing the other entry lets the next setup migrate and clear the issue."""
    other = _add_entry(hass, "192.168.1.10", "GARDENA-123456")
    duplicate = _add_entry(hass, "192.168.1.11", "192.168.1.11")
    with patch(PATCH_EXTRACT_HOSTNAME, return_value="GARDENA-123456"):
        await _async_migrate_unique_id(hass, duplicate)
    await hass.config_entries.async_remove(other.entry_id)

    with patch(PATCH_EXTRACT_HOSTNAME, return_value="GARDENA-123456"):
        await _async_migrate_unique_id(hass, duplicate)

    assert duplicate.unique_id == "GARDENA-123456"
    assert (
        ir.async_get(hass).async_get_issue(
            DOMAIN, f"duplicate_gateway_{duplicate.entry_id}"
        )
        is None
    )
