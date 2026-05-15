# SPDX-FileCopyrightText: 2026 GARDENA GmbH
#
# SPDX-License-Identifier: Apache-2.0

"""GARDENA smart SILENO mower entity."""

from __future__ import annotations

import logging

from gardena_smart_local_api.devices import Device, MowerState

from homeassistant.components.lawn_mower import (
    LawnMowerActivity,
    LawnMowerEntity,
    LawnMowerEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import GardenaSmartLocalCoordinator
from .entity import GardenaEntity, find_device_subentry_id

_LOGGER = logging.getLogger(__name__)


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
            if (
                hasattr(device, "build_start_mowing_obj")
                and device.id not in known_devices
            ):
                known_devices.add(device.id)
                sid = find_device_subentry_id(entry, device.id)
                entities_by_subentry_id.setdefault(sid, []).append(
                    GardenaMower(coordinator, device)
                )
                _LOGGER.info("Adding new mower entity for device %s", device.id)
        for sid, entities in entities_by_subentry_id.items():
            async_add_entities(entities, config_subentry_id=sid)

    coordinator.async_add_listener(_add_new_devices)


class GardenaMower(GardenaEntity, LawnMowerEntity):
    def __init__(
        self,
        coordinator: GardenaSmartLocalCoordinator,
        device: Device,
    ) -> None:
        super().__init__(coordinator, device)
        self._attr_unique_id = f"{device.id}_lawn_mower"
        self._attr_name = None
        self._attr_reports_position = False
        self._attr_supported_features = (
            LawnMowerEntityFeature.DOCK | LawnMowerEntityFeature.START_MOWING
        )
        if hasattr(device, "build_pause_mowing_obj"):
            self._attr_supported_features |= LawnMowerEntityFeature.PAUSE

    @property
    def activity(self) -> LawnMowerActivity:
        mower_state = self._device.state
        _LOGGER.debug("Mower status: %s", mower_state)
        if hasattr(self._device, "_status"):
            _LOGGER.debug(f"DBG: {self._device._status}")
        match mower_state:
            case MowerState.CHARGING | MowerState.PARKED:
                return LawnMowerActivity.DOCKED

            case MowerState.LEAVING | MowerState.MOWING:
                return LawnMowerActivity.MOWING

            case MowerState.PAUSED:
                return LawnMowerActivity.PAUSED

            case MowerState.RETURNING:
                return LawnMowerActivity.RETURNING

        return LawnMowerActivity.ERROR

    async def async_start_mowing(self) -> None:
        await self.coordinator.send_request(
            self._device.id,
            self._device.build_start_mowing_obj(28800),  # 8 hours
        )
        _LOGGER.info("Start mowing with %s", self._device.id)

    async def async_dock(self) -> None:
        await self.coordinator.send_request(
            self._device.id,
            self._device.build_stop_mowing_obj(),
        )
        _LOGGER.info("Stop mowing with %s", self._device.id)

    async def async_pause(self) -> None:
        if hasattr(self._device, "build_pause_mowing_obj"):
            await self.coordinator.send_request(
                self._device.id,
                self._device.build_pause_mowing_obj(),
            )
            _LOGGER.info("Pause mowing with %s", self._device.id)
        else:
            _LOGGER.warning("Pause not supported for device %s", self._device.id)
