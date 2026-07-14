# SPDX-FileCopyrightText: 2026 GARDENA GmbH
#
# SPDX-License-Identifier: Apache-2.0

"""Tests for the GARDENA smart local firmware update entity."""

from __future__ import annotations

from unittest.mock import AsyncMock

from gardena_smart_local_api.devices import Gen1WaterControl
from gardena_smart_local_api.devices.device import FirmwareUpdateState

from custom_components.gardena_smart_local_preview import update


# ---------------------------------------------------------------------------
# async_setup_entry
# ---------------------------------------------------------------------------


async def test_setup_adds_update_entity_for_device(
    coordinator, entry, setup_platform, spec_device, sync_devices
) -> None:
    async_add_entities = await setup_platform(update, entry)
    device = spec_device(Gen1WaterControl, device_id="device-1")
    coordinator._devices["device-1"] = device
    sync_devices()

    async_add_entities.assert_called_once()
    (entities,), kwargs = async_add_entities.call_args
    assert len(entities) == 1
    assert isinstance(entities[0], update.GardenaFirmwareUpdate)
    assert kwargs["config_subentry_id"] is None


async def test_setup_noop_when_coordinator_data_empty(
    coordinator, entry, setup_platform, sync_devices
) -> None:
    async_add_entities = await setup_platform(update, entry)
    sync_devices()
    async_add_entities.assert_not_called()


async def test_setup_dedups_on_repeated_firing(
    coordinator, entry, setup_platform, spec_device, sync_devices
) -> None:
    async_add_entities = await setup_platform(update, entry)
    device = spec_device(Gen1WaterControl, device_id="device-1")
    coordinator._devices["device-1"] = device

    sync_devices()
    sync_devices()

    async_add_entities.assert_called_once()


# ---------------------------------------------------------------------------
# installed_version / latest_version
# ---------------------------------------------------------------------------


def test_installed_version_returns_software_version(
    coordinator, spec_device, sync_devices
) -> None:
    device = spec_device(Gen1WaterControl, device_id="device-1", software_version="1.0")
    coordinator._devices["device-1"] = device
    sync_devices()
    entity = update.GardenaFirmwareUpdate(coordinator, device)
    assert entity.installed_version == "1.0"


def test_installed_version_none_when_device_missing(
    coordinator, spec_device, sync_devices
) -> None:
    device = spec_device(Gen1WaterControl, device_id="device-1")
    sync_devices()
    entity = update.GardenaFirmwareUpdate(coordinator, device)
    assert entity.installed_version is None


def test_latest_version_none_when_device_missing(
    coordinator, spec_device, sync_devices
) -> None:
    device = spec_device(Gen1WaterControl, device_id="device-1")
    sync_devices()
    entity = update.GardenaFirmwareUpdate(coordinator, device)
    assert entity.latest_version is None


def test_latest_version_downloaded_uses_available_version(
    coordinator, spec_device, sync_devices
) -> None:
    device = spec_device(
        Gen1WaterControl,
        device_id="device-1",
        firmware_update_state=FirmwareUpdateState.DOWNLOADED,
        available_software_version="2.0",
        software_version="1.0",
    )
    coordinator._devices["device-1"] = device
    sync_devices()
    entity = update.GardenaFirmwareUpdate(coordinator, device)
    assert entity.latest_version == "2.0"


def test_latest_version_downloaded_falls_back_to_installed(
    coordinator, spec_device, sync_devices
) -> None:
    device = spec_device(
        Gen1WaterControl,
        device_id="device-1",
        firmware_update_state=FirmwareUpdateState.DOWNLOADED,
        available_software_version=None,
        software_version="1.0",
    )
    coordinator._devices["device-1"] = device
    sync_devices()
    entity = update.GardenaFirmwareUpdate(coordinator, device)
    assert entity.latest_version == "1.0"


def test_latest_version_updating_uses_held_version(
    coordinator, spec_device, sync_devices
) -> None:
    device = spec_device(
        Gen1WaterControl,
        device_id="device-1",
        firmware_update_state=FirmwareUpdateState.UPDATING,
        available_software_version="2.0",
        software_version="1.0",
    )
    coordinator._devices["device-1"] = device
    sync_devices()
    entity = update.GardenaFirmwareUpdate(coordinator, device)
    entity._held_latest_version = "1.9"
    assert entity.latest_version == "1.9"


def test_latest_version_updating_falls_back_to_available_then_installed(
    coordinator, spec_device, sync_devices
) -> None:
    device = spec_device(
        Gen1WaterControl,
        device_id="device-1",
        firmware_update_state=FirmwareUpdateState.UPDATING,
        available_software_version="2.0",
        software_version="1.0",
    )
    coordinator._devices["device-1"] = device
    sync_devices()
    entity = update.GardenaFirmwareUpdate(coordinator, device)
    assert entity.latest_version == "2.0"


def test_latest_version_idle_returns_installed_version(
    coordinator, spec_device, sync_devices
) -> None:
    device = spec_device(
        Gen1WaterControl,
        device_id="device-1",
        firmware_update_state=FirmwareUpdateState.IDLE,
        available_software_version="2.0",
        software_version="1.0",
    )
    coordinator._devices["device-1"] = device
    sync_devices()
    entity = update.GardenaFirmwareUpdate(coordinator, device)
    assert entity.latest_version == "1.0"


def test_latest_version_downloading_returns_installed_version(
    coordinator, spec_device, sync_devices
) -> None:
    device = spec_device(
        Gen1WaterControl,
        device_id="device-1",
        firmware_update_state=FirmwareUpdateState.DOWNLOADING,
        available_software_version="2.0",
        software_version="1.0",
    )
    coordinator._devices["device-1"] = device
    sync_devices()
    entity = update.GardenaFirmwareUpdate(coordinator, device)
    assert entity.latest_version == "1.0"


# ---------------------------------------------------------------------------
# _handle_coordinator_update: held target version while updating
# ---------------------------------------------------------------------------


def test_handle_coordinator_update_holds_version_on_entering_updating(
    coordinator, spec_device, sync_devices
) -> None:
    device = spec_device(
        Gen1WaterControl,
        device_id="device-1",
        firmware_update_state=FirmwareUpdateState.UPDATING,
        available_software_version="2.0",
    )
    coordinator._devices["device-1"] = device
    sync_devices()
    entity = update.GardenaFirmwareUpdate(coordinator, device)
    entity.async_write_ha_state = lambda: None

    entity._handle_coordinator_update()

    assert entity._held_latest_version == "2.0"


def test_handle_coordinator_update_keeps_existing_held_version(
    coordinator, spec_device, sync_devices
) -> None:
    device = spec_device(
        Gen1WaterControl,
        device_id="device-1",
        firmware_update_state=FirmwareUpdateState.UPDATING,
        available_software_version="2.0",
    )
    coordinator._devices["device-1"] = device
    sync_devices()
    entity = update.GardenaFirmwareUpdate(coordinator, device)
    entity.async_write_ha_state = lambda: None
    entity._held_latest_version = "1.9"

    entity._handle_coordinator_update()

    assert entity._held_latest_version == "1.9"


def test_handle_coordinator_update_clears_held_version_when_not_in_progress(
    coordinator, spec_device, sync_devices
) -> None:
    device = spec_device(
        Gen1WaterControl,
        device_id="device-1",
        firmware_update_state=FirmwareUpdateState.IDLE,
    )
    coordinator._devices["device-1"] = device
    sync_devices()
    entity = update.GardenaFirmwareUpdate(coordinator, device)
    entity.async_write_ha_state = lambda: None
    entity._held_latest_version = "1.9"

    entity._handle_coordinator_update()

    assert entity._held_latest_version is None


def test_handle_coordinator_update_noop_when_device_missing(
    coordinator, spec_device, sync_devices
) -> None:
    device = spec_device(Gen1WaterControl, device_id="device-1")
    sync_devices()
    entity = update.GardenaFirmwareUpdate(coordinator, device)
    entity.async_write_ha_state = lambda: None
    entity._held_latest_version = "1.9"

    entity._handle_coordinator_update()

    assert entity._held_latest_version == "1.9"


# ---------------------------------------------------------------------------
# version_is_newer / in_progress
# ---------------------------------------------------------------------------


def test_version_is_newer_true_for_downgrade(coordinator, spec_device) -> None:
    device = spec_device(Gen1WaterControl, device_id="device-1")
    entity = update.GardenaFirmwareUpdate(coordinator, device)
    assert entity.version_is_newer("1.0", "2.0") is True


def test_version_is_newer_false_when_equal(coordinator, spec_device) -> None:
    device = spec_device(Gen1WaterControl, device_id="device-1")
    entity = update.GardenaFirmwareUpdate(coordinator, device)
    assert entity.version_is_newer("1.0", "1.0") is False


def test_in_progress_true_when_updating(coordinator, spec_device, sync_devices) -> None:
    device = spec_device(
        Gen1WaterControl,
        device_id="device-1",
        firmware_update_state=FirmwareUpdateState.UPDATING,
    )
    coordinator._devices["device-1"] = device
    sync_devices()
    entity = update.GardenaFirmwareUpdate(coordinator, device)
    assert entity.in_progress is True


def test_in_progress_false_when_idle(coordinator, spec_device, sync_devices) -> None:
    device = spec_device(
        Gen1WaterControl,
        device_id="device-1",
        firmware_update_state=FirmwareUpdateState.IDLE,
    )
    coordinator._devices["device-1"] = device
    sync_devices()
    entity = update.GardenaFirmwareUpdate(coordinator, device)
    assert entity.in_progress is False


def test_in_progress_false_when_device_missing(
    coordinator, spec_device, sync_devices
) -> None:
    device = spec_device(Gen1WaterControl, device_id="device-1")
    sync_devices()
    entity = update.GardenaFirmwareUpdate(coordinator, device)
    assert entity.in_progress is False


# ---------------------------------------------------------------------------
# async_install / async_added_to_hass
# ---------------------------------------------------------------------------


async def test_async_install_holds_version_and_sends_request(
    coordinator, spec_device, sync_devices
) -> None:
    device = spec_device(
        Gen1WaterControl, device_id="device-1", available_software_version="2.0"
    )
    coordinator._devices["device-1"] = device
    sync_devices()
    coordinator.send_request = AsyncMock()
    entity = update.GardenaFirmwareUpdate(coordinator, device)

    await entity.async_install(version="2.0", backup=False)

    assert entity._held_latest_version == "2.0"
    device.build_install_firmware_update_obj.assert_called_once_with()
    coordinator.send_request.assert_awaited_once_with(
        "device-1", device.build_install_firmware_update_obj.return_value
    )


async def test_async_install_noop_hold_when_device_missing(
    coordinator, spec_device, sync_devices
) -> None:
    device = spec_device(Gen1WaterControl, device_id="device-1")
    sync_devices()
    coordinator.send_request = AsyncMock()
    entity = update.GardenaFirmwareUpdate(coordinator, device)

    await entity.async_install(version="2.0", backup=False)

    assert entity._held_latest_version is None
    coordinator.send_request.assert_awaited_once()


async def test_async_added_to_hass_refreshes_firmware(
    coordinator, spec_device, sync_devices
) -> None:
    device = spec_device(Gen1WaterControl, device_id="device-1")
    coordinator._devices["device-1"] = device
    sync_devices()
    coordinator.async_refresh_firmware = AsyncMock()
    entity = update.GardenaFirmwareUpdate(coordinator, device)
    entity.hass = coordinator.hass

    await entity.async_added_to_hass()

    coordinator.async_refresh_firmware.assert_awaited_once_with("device-1")
