# SPDX-FileCopyrightText: 2026 GARDENA GmbH
#
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from functools import partial

from gardena_smart_local_api.devices.device import Device
from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import GardenaSmartLocalCoordinator
from .entity import EntityFactories, GardenaEntity, async_setup_device_entities

# State comes only from the coordinator's push (no polling, no actions) —
# there is nothing here for PARALLEL_UPDATES to throttle
PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator: GardenaSmartLocalCoordinator = entry.runtime_data

    def _entities_for_device(device: Device) -> EntityFactories:
        entities: EntityFactories = {}
        if hasattr(device, "has_frost_warning"):
            entities["frost_warning"] = partial(
                GardenaFrostWarningSensor, coordinator, device
            )
        return entities

    async_setup_device_entities(
        entry, coordinator, async_add_entities, _entities_for_device
    )


class GardenaFrostWarningSensor(GardenaEntity, BinarySensorEntity):
    def __init__(
        self,
        coordinator: GardenaSmartLocalCoordinator,
        device: Device,
    ) -> None:
        super().__init__(coordinator, device)
        self._attr_unique_id = f"{device.id}_frost_warning"
        self._attr_translation_key = "frost_warning"
        self._attr_device_class = BinarySensorDeviceClass.COLD
        self._attr_icon = "mdi:snowflake-alert"

    @property
    def is_on(self) -> bool | None:
        device = self.coordinator.data.get(self._device.id)
        if not device:
            return None
        return device.has_frost_warning
