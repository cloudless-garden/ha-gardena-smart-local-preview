# SPDX-FileCopyrightText: 2026 GARDENA GmbH
#
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.update import (
    UpdateDeviceClass,
    UpdateEntity,
    UpdateEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import GardenaSmartLocalCoordinator
from .entity import GardenaEntity, find_device_subentry_id
from gardena_smart_local_api.devices.device import Device, FirmwareUpdateState

_LOGGER = logging.getLogger(__name__)

_IN_PROGRESS_STATES = (FirmwareUpdateState.UPDATING,)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator: GardenaSmartLocalCoordinator = entry.runtime_data
    known_devices: set[str] = set()

    def _add_new_devices() -> None:
        if not coordinator.data:
            return
        known_devices.intersection_update(coordinator.data)
        entities_by_subentry_id: dict[str | None, list] = {}
        for device in coordinator.data.values():
            if device.id in known_devices:
                continue
            known_devices.add(device.id)
            sid = find_device_subentry_id(entry, device.id)
            entities_by_subentry_id.setdefault(sid, []).append(
                GardenaFirmwareUpdate(coordinator, device)
            )
            _LOGGER.info("Adding firmware update entity for device %s", device.id)
        for sid, entities in entities_by_subentry_id.items():
            async_add_entities(entities, config_subentry_id=sid)

    coordinator.async_add_listener(_add_new_devices)


class GardenaFirmwareUpdate(GardenaEntity, UpdateEntity):
    _attr_device_class = UpdateDeviceClass.FIRMWARE
    _attr_supported_features = (
        UpdateEntityFeature.INSTALL | UpdateEntityFeature.PROGRESS
    )

    def __init__(
        self,
        coordinator: GardenaSmartLocalCoordinator,
        device: Device,
    ) -> None:
        super().__init__(coordinator, device)
        self._attr_unique_id = f"{device.id}_firmware"
        self._held_latest_version: str | None = None

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        await self.coordinator.async_refresh_firmware(self._device.id)

    @property
    def installed_version(self) -> str | None:
        device = self.coordinator.data.get(self._device.id)
        return device.software_version if device else None

    @property
    def latest_version(self) -> str | None:
        device = self.coordinator.data.get(self._device.id)
        if not device:
            return None
        state = device.firmware_update_state
        if state == FirmwareUpdateState.DOWNLOADED:
            return device.available_software_version or device.software_version
        if state in _IN_PROGRESS_STATES:
            return (
                self._held_latest_version
                or device.available_software_version
                or device.software_version
            )
        # IDLE or DOWNLOADING: package not ready yet, do not offer an update
        return device.software_version

    @callback
    def _handle_coordinator_update(self) -> None:
        """Hold the target version while an update is running.

        The gateway clears or rewrites pkg_version while flashing, which
        would make latest_version flap until the update finishes.
        """
        device = self.coordinator.data.get(self._device.id)
        if device:
            if device.firmware_update_state in _IN_PROGRESS_STATES:
                if self._held_latest_version is None:
                    self._held_latest_version = device.available_software_version
            else:
                self._held_latest_version = None
        super()._handle_coordinator_update()

    def version_is_newer(self, latest_version: str, installed_version: str) -> bool:
        """Check if versions differ, allowing downgrades as valid updates."""
        return latest_version != installed_version

    @property
    def in_progress(self) -> bool:
        device = self.coordinator.data.get(self._device.id)
        return bool(device and device.firmware_update_state in _IN_PROGRESS_STATES)

    async def async_install(
        self, version: str | None, backup: bool, **kwargs: Any
    ) -> None:
        device = self.coordinator.data.get(self._device.id)
        if device:
            self._held_latest_version = device.available_software_version
        await self.coordinator.send_request(
            self._device.id,
            self._device.build_install_firmware_update_obj(),
        )
        _LOGGER.info("Sent firmware install request for device %s", self._device.id)
