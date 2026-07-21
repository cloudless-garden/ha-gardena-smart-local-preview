# SPDX-FileCopyrightText: 2026 GARDENA GmbH
#
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import GardenaSmartLocalCoordinator
from gardena_smart_local_api.devices.device import Device


def find_device_subentry_id(entry: ConfigEntry, device_id: str) -> str | None:
    return next(
        (
            sid
            for sid, se in entry.subentries.items()
            if se.data.get("device_id") == device_id
        ),
        None,
    )


class GardenaEntity(CoordinatorEntity[GardenaSmartLocalCoordinator]):
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: GardenaSmartLocalCoordinator,
        device: Device,
    ) -> None:
        super().__init__(coordinator)
        self._device = device
        self._attr_device_info = dr.DeviceInfo(
            identifiers={(DOMAIN, device.id)},
            name=f"GARDENA {device.model_definition.name} {device.serial_number}",
            manufacturer="GARDENA",
            model=device.model_definition.name,
            model_id=device.model_definition.model_number,
            sw_version=device.software_version,
            hw_version=device.hardware_version,
            serial_number=device.serial_number,
        )

    @property
    def available(self) -> bool:
        if not self.coordinator.connected:
            return False
        device = self.coordinator.data.get(self._device.id)
        return bool(device and device.is_online)

    @callback
    def _handle_coordinator_update(self) -> None:
        """Keep the device registry sw_version in sync.

        DeviceInfo is only applied when the entity is added, so after a
        firmware up-/downgrade the device page would keep showing the old
        version until Home Assistant restarts.
        """
        device = self.coordinator.data.get(self._device.id)
        if (
            device
            and device.software_version
            and self.device_entry
            and self.device_entry.sw_version != device.software_version
        ):
            dr.async_get(self.hass).async_update_device(
                self.device_entry.id, sw_version=device.software_version
            )
        super()._handle_coordinator_update()
