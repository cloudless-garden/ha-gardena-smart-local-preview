# SPDX-FileCopyrightText: 2026 GARDENA GmbH
#
# SPDX-License-Identifier: Apache-2.0

"""Tests for the GARDENA smart local integration setup/unload."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp

from homeassistant.config_entries import (
    SIGNAL_CONFIG_ENTRY_CHANGED,
    ConfigEntryChange,
    ConfigEntryState,
)
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_PORT
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.dispatcher import async_dispatcher_send
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.gardena_smart_local_preview import DOMAIN, async_setup
from custom_components.gardena_smart_local_preview.coordinator import (
    GardenaSmartLocalCoordinator,
)

PATCH_CONNECT = (
    "custom_components.gardena_smart_local_preview.coordinator."
    "GardenaSmartLocalCoordinator.async_connect"
)
PATCH_DISCONNECT = (
    "custom_components.gardena_smart_local_preview.coordinator."
    "GardenaSmartLocalCoordinator.async_disconnect"
)


def _mock_connect():
    return patch(PATCH_CONNECT, AsyncMock())


def _mock_disconnect():
    return patch(PATCH_DISCONNECT, AsyncMock())


async def test_async_setup_without_domain_config_is_noop(hass) -> None:
    result = await async_setup(hass, {})

    assert result is True
    assert hass.config_entries.async_entries(DOMAIN) == []


async def test_async_setup_imports_yaml_config(hass) -> None:
    with _mock_connect(), _mock_disconnect():
        result = await async_setup(
            hass,
            {
                DOMAIN: {
                    CONF_HOST: "192.168.1.50",
                    CONF_PORT: 8443,
                    CONF_PASSWORD: "secret",
                }
            },
        )
        await hass.async_block_till_done()

    assert result is True
    entries = hass.config_entries.async_entries(DOMAIN)
    assert len(entries) == 1
    assert entries[0].data[CONF_HOST] == "192.168.1.50"


async def test_setup_entry_connects_and_forwards_platforms(hass) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_HOST: "192.168.1.50", CONF_PORT: 8443, CONF_PASSWORD: "secret"},
    )
    entry.add_to_hass(hass)

    with _mock_connect() as mock_connect, _mock_disconnect():
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.LOADED
    assert isinstance(entry.runtime_data, GardenaSmartLocalCoordinator)
    mock_connect.assert_called_once()


async def test_setup_entry_retries_on_connect_failure(hass) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_HOST: "192.168.1.50", CONF_PORT: 8443, CONF_PASSWORD: "secret"},
    )
    entry.add_to_hass(hass)

    with (
        patch(PATCH_CONNECT, AsyncMock(side_effect=RuntimeError("boom"))),
        patch(PATCH_DISCONNECT, AsyncMock()) as mock_disconnect,
    ):
        assert not await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.SETUP_RETRY
    mock_disconnect.assert_called_once()


async def test_setup_entry_fails_auth_on_401(hass) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_HOST: "192.168.1.50", CONF_PORT: 8443, CONF_PASSWORD: "secret"},
    )
    entry.add_to_hass(hass)
    error = aiohttp.WSServerHandshakeError(
        request_info=MagicMock(), history=(), status=401, message="Unauthorized"
    )

    with (
        patch(PATCH_CONNECT, AsyncMock(side_effect=error)),
        patch(PATCH_DISCONNECT, AsyncMock()) as mock_disconnect,
    ):
        assert not await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.SETUP_ERROR
    mock_disconnect.assert_called_once()
    flows = hass.config_entries.flow.async_progress_by_handler(DOMAIN)
    assert any(flow["context"]["source"] == "reauth" for flow in flows)


async def test_setup_entry_non_401_handshake_error_retries(hass) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_HOST: "192.168.1.50", CONF_PORT: 8443, CONF_PASSWORD: "secret"},
    )
    entry.add_to_hass(hass)
    error = aiohttp.WSServerHandshakeError(
        request_info=MagicMock(), history=(), status=500, message="Server error"
    )

    with (
        patch(PATCH_CONNECT, AsyncMock(side_effect=error)),
        patch(PATCH_DISCONNECT, AsyncMock()) as mock_disconnect,
    ):
        assert not await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.SETUP_RETRY
    mock_disconnect.assert_called_once()


async def test_setup_entry_creates_subentry_for_discovered_device(
    hass, mock_device
) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_HOST: "192.168.1.50", CONF_PORT: 8443, CONF_PASSWORD: "secret"},
    )
    entry.add_to_hass(hass)

    with _mock_connect(), _mock_disconnect():
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        coordinator = entry.runtime_data
        device = mock_device(device_id="device-1", name="Water Control")
        coordinator._devices["device-1"] = device
        coordinator.async_set_updated_data(coordinator._devices)
        await hass.async_block_till_done()

        assert await hass.config_entries.async_unload(entry.entry_id)
        await hass.async_block_till_done()

    subentries = list(entry.subentries.values())
    assert len(subentries) == 1
    assert subentries[0].data["device_id"] == "device-1"
    assert subentries[0].title == "Water Control SN123"


async def test_setup_entry_migrates_legacy_device_to_subentry(
    hass, mock_device
) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_HOST: "192.168.1.50", CONF_PORT: 8443, CONF_PASSWORD: "secret"},
    )
    entry.add_to_hass(hass)

    dev_reg = dr.async_get(hass)
    legacy_device = dev_reg.async_get_or_create(
        config_entry_id=entry.entry_id,
        config_subentry_id=None,
        identifiers={(DOMAIN, "device-1")},
    )

    with _mock_connect(), _mock_disconnect():
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        coordinator = entry.runtime_data
        device = mock_device(device_id="device-1", name="Water Control")
        coordinator._devices["device-1"] = device
        coordinator.async_set_updated_data(coordinator._devices)
        await hass.async_block_till_done()

        assert await hass.config_entries.async_unload(entry.entry_id)
        await hass.async_block_till_done()

    updated_device = dev_reg.async_get(legacy_device.id)
    assert updated_device is not None
    subentry_id = next(iter(entry.subentries.keys()))
    assert None not in updated_device.config_entries_subentries.get(
        entry.entry_id, set()
    )
    assert subentry_id in updated_device.config_entries_subentries.get(
        entry.entry_id, set()
    )


async def test_entry_updated_excludes_device_when_subentry_removed(
    hass, mock_device
) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_HOST: "192.168.1.50", CONF_PORT: 8443, CONF_PASSWORD: "secret"},
    )
    entry.add_to_hass(hass)

    with _mock_connect(), _mock_disconnect():
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        coordinator = entry.runtime_data
        device = mock_device(device_id="device-1", name="Water Control")
        coordinator._devices["device-1"] = device
        coordinator.async_set_updated_data(coordinator._devices)
        await hass.async_block_till_done()

        # Sync the closure's known-subentries cache with reality.
        async_dispatcher_send(
            hass, SIGNAL_CONFIG_ENTRY_CHANGED, ConfigEntryChange.UPDATED, entry
        )
        await hass.async_block_till_done()

        subentry_id = next(iter(entry.subentries.keys()))

        with patch.object(
            GardenaSmartLocalCoordinator, "async_exclude_device", AsyncMock()
        ) as mock_exclude:
            # Removing the subentry fires SIGNAL_CONFIG_ENTRY_CHANGED itself.
            hass.config_entries.async_remove_subentry(entry, subentry_id)
            await hass.async_block_till_done()

        assert await hass.config_entries.async_unload(entry.entry_id)
        await hass.async_block_till_done()

    mock_exclude.assert_called_once_with("device-1")


async def test_unload_entry_disconnects_coordinator(hass) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_HOST: "192.168.1.50", CONF_PORT: 8443, CONF_PASSWORD: "secret"},
    )
    entry.add_to_hass(hass)

    with _mock_connect(), _mock_disconnect() as mock_disconnect:
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        assert await hass.config_entries.async_unload(entry.entry_id)
        await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.NOT_LOADED
    mock_disconnect.assert_called_once()
