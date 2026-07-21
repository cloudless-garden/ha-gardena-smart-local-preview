# SPDX-FileCopyrightText: 2026 GARDENA GmbH
#
# SPDX-License-Identifier: Apache-2.0

"""Tests for the GARDENA smart local shared entity base."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from homeassistant.helpers import device_registry as dr
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.gardena_smart_local_preview.const import DOMAIN
from custom_components.gardena_smart_local_preview.entity import (
    GardenaEntity,
    find_device_subentry_id,
)

PATCH_DR_ASYNC_GET = "custom_components.gardena_smart_local_preview.entity.dr.async_get"


def _make_entity_for_update_test(
    coordinator, device
) -> tuple[GardenaEntity, MagicMock]:
    """Build a GardenaEntity wired up enough to exercise _handle_coordinator_update."""
    entity = GardenaEntity(coordinator, device)
    entity.hass = MagicMock()
    entity.async_write_ha_state = MagicMock()
    entity.device_entry = MagicMock(id="registry-device-id", sw_version="0.9")
    return entity, entity.device_entry


def _make_entry_with_subentries(subentries: dict) -> MockConfigEntry:
    entry = MockConfigEntry(domain=DOMAIN, data={})
    entry.subentries = subentries
    return entry


def _make_subentry(device_id: str) -> MagicMock:
    subentry = MagicMock()
    subentry.data = {"device_id": device_id}
    return subentry


def test_find_device_subentry_id_match() -> None:
    entry = _make_entry_with_subentries({"sub-1": _make_subentry("device-1")})
    assert find_device_subentry_id(entry, "device-1") == "sub-1"


def test_find_device_subentry_id_no_match() -> None:
    entry = _make_entry_with_subentries({"sub-1": _make_subentry("device-1")})
    assert find_device_subentry_id(entry, "device-2") is None


def test_find_device_subentry_id_empty_subentries() -> None:
    entry = _make_entry_with_subentries({})
    assert find_device_subentry_id(entry, "device-1") is None


def test_gardena_entity_device_info(mock_device) -> None:
    device = mock_device(
        device_id="device-1",
        name="Water Control",
        model_number="MOD-1",
        serial_number="SN123",
    )
    coordinator = MagicMock()

    entity = GardenaEntity(coordinator, device)

    assert entity._attr_device_info == dr.DeviceInfo(
        identifiers={(DOMAIN, "device-1")},
        name="GARDENA Water Control SN123",
        manufacturer="GARDENA",
        model="Water Control",
        model_id="MOD-1",
        sw_version="1.0",
        hw_version="2.0",
        serial_number="SN123",
    )


def test_gardena_entity_available_when_online(mock_device) -> None:
    device = mock_device(device_id="device-1", is_online=True)
    coordinator = MagicMock()
    coordinator.data = {"device-1": device}

    entity = GardenaEntity(coordinator, device)

    assert entity.available is True


def test_gardena_entity_unavailable_when_offline(mock_device) -> None:
    device = mock_device(device_id="device-1", is_online=False)
    coordinator = MagicMock()
    coordinator.data = {"device-1": device}

    entity = GardenaEntity(coordinator, device)

    assert entity.available is False


def test_gardena_entity_unavailable_when_missing_from_coordinator_data(
    mock_device,
) -> None:
    device = mock_device(device_id="device-1", is_online=True)
    coordinator = MagicMock()
    coordinator.data = {}

    entity = GardenaEntity(coordinator, device)

    assert entity.available is False


def test_gardena_entity_unavailable_when_gateway_disconnected(mock_device) -> None:
    device = mock_device(device_id="device-1", is_online=True)
    coordinator = MagicMock()
    coordinator.data = {"device-1": device}
    coordinator.connected = False

    entity = GardenaEntity(coordinator, device)

    assert entity.available is False


# ---------------------------------------------------------------------------
# _handle_coordinator_update: device registry sw_version sync
# ---------------------------------------------------------------------------


def test_handle_coordinator_update_syncs_changed_sw_version(mock_device) -> None:
    device = mock_device(device_id="device-1")
    device.software_version = "1.1"
    coordinator = MagicMock()
    coordinator.data = {"device-1": device}

    entity, device_entry = _make_entity_for_update_test(coordinator, device)
    dev_reg = MagicMock()

    with patch(PATCH_DR_ASYNC_GET, return_value=dev_reg):
        entity._handle_coordinator_update()

    dev_reg.async_update_device.assert_called_once_with(
        device_entry.id, sw_version="1.1"
    )
    entity.async_write_ha_state.assert_called_once()


def test_handle_coordinator_update_noop_when_sw_version_unchanged(mock_device) -> None:
    device = mock_device(device_id="device-1")
    device.software_version = "0.9"
    coordinator = MagicMock()
    coordinator.data = {"device-1": device}

    entity, _ = _make_entity_for_update_test(coordinator, device)
    dev_reg = MagicMock()

    with patch(PATCH_DR_ASYNC_GET, return_value=dev_reg):
        entity._handle_coordinator_update()

    dev_reg.async_update_device.assert_not_called()
    entity.async_write_ha_state.assert_called_once()


def test_handle_coordinator_update_noop_when_device_missing(mock_device) -> None:
    device = mock_device(device_id="device-1")
    device.software_version = "1.1"
    coordinator = MagicMock()
    coordinator.data = {}

    entity, _ = _make_entity_for_update_test(coordinator, device)
    dev_reg = MagicMock()

    with patch(PATCH_DR_ASYNC_GET, return_value=dev_reg):
        entity._handle_coordinator_update()

    dev_reg.async_update_device.assert_not_called()
    entity.async_write_ha_state.assert_called_once()


def test_handle_coordinator_update_noop_when_no_software_version(mock_device) -> None:
    device = mock_device(device_id="device-1")
    device.software_version = None
    coordinator = MagicMock()
    coordinator.data = {"device-1": device}

    entity, _ = _make_entity_for_update_test(coordinator, device)
    dev_reg = MagicMock()

    with patch(PATCH_DR_ASYNC_GET, return_value=dev_reg):
        entity._handle_coordinator_update()

    dev_reg.async_update_device.assert_not_called()
    entity.async_write_ha_state.assert_called_once()


def test_handle_coordinator_update_noop_when_no_device_entry(mock_device) -> None:
    device = mock_device(device_id="device-1")
    device.software_version = "1.1"
    coordinator = MagicMock()
    coordinator.data = {"device-1": device}

    entity, _ = _make_entity_for_update_test(coordinator, device)
    entity.device_entry = None
    dev_reg = MagicMock()

    with patch(PATCH_DR_ASYNC_GET, return_value=dev_reg):
        entity._handle_coordinator_update()

    dev_reg.async_update_device.assert_not_called()
    entity.async_write_ha_state.assert_called_once()
