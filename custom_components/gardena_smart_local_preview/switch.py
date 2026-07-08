# SPDX-FileCopyrightText: 2026 GARDENA GmbH
#
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.switch import SwitchDeviceClass, SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import GardenaSmartLocalCoordinator
from .entity import GardenaEntity, find_device_subentry_id
from gardena_smart_local_api.devices import PowerAdapter, Pump

_LOGGER = logging.getLogger(__name__)

# Actions send commands to the gateway's local websocket — cap at 1 so HA
# serializes them instead of firing concurrent commands at the same connection
PARALLEL_UPDATES = 1

# used as "indefinitly" in the official app
DEFAULT_ON_DURATION_SECONDS = 16777216


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
            if isinstance(device, PowerAdapter) and device.id not in known_devices:
                known_devices.add(device.id)
                sid = find_device_subentry_id(entry, device.id)
                entities_by_subentry_id.setdefault(sid, []).append(
                    GardenaPowerSwitch(coordinator, device)
                )
                _LOGGER.info("Adding new switch entity for device %s", device.id)
            elif isinstance(device, Pump) and device.id not in known_devices:
                known_devices.add(device.id)
                sid = find_device_subentry_id(entry, device.id)
                entities_by_subentry_id.setdefault(sid, []).append(
                    GardenaPumpSwitch(coordinator, device)
                )
                _LOGGER.info("Adding new pump switch entity for device %s", device.id)
        for sid, entities in entities_by_subentry_id.items():
            async_add_entities(entities, config_subentry_id=sid)

    coordinator.async_add_listener(_add_new_devices)


class GardenaPowerSwitch(GardenaEntity, SwitchEntity):
    def __init__(
        self,
        coordinator: GardenaSmartLocalCoordinator,
        device: PowerAdapter,
    ) -> None:
        super().__init__(coordinator, device)
        self._attr_unique_id = f"{device.id}_switch"
        self._attr_name = None
        self._attr_device_class = SwitchDeviceClass.OUTLET

    @property
    def is_on(self) -> bool | None:
        device = self.coordinator.data.get(self._device.id)
        if not device:
            return None
        return device.is_output_enabled

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.coordinator.send_request(
            self._device.id,
            self._device.build_enable_output_obj(DEFAULT_ON_DURATION_SECONDS),
        )
        _LOGGER.info("Turning on switch %s", self._device.id)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.coordinator.send_request(
            self._device.id,
            self._device.build_disable_output_obj(),
        )
        _LOGGER.info("Turning off switch %s", self._device.id)


class GardenaPumpSwitch(GardenaEntity, SwitchEntity):
    def __init__(
        self,
        coordinator: GardenaSmartLocalCoordinator,
        device: Pump,
    ) -> None:
        super().__init__(coordinator, device)
        self._attr_unique_id = f"{device.id}_switch"
        self._attr_name = None

    @property
    def is_on(self) -> bool | None:
        device = self.coordinator.data.get(self._device.id)
        if not device:
            return None
        return device.is_running

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.coordinator.send_request(
            self._device.id,
            self._device.build_start_obj(DEFAULT_ON_DURATION_SECONDS),
        )
        _LOGGER.info("Turning on pump %s", self._device.id)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.coordinator.send_request(
            self._device.id,
            self._device.build_stop_obj(),
        )
        _LOGGER.info("Turning off pump %s", self._device.id)
