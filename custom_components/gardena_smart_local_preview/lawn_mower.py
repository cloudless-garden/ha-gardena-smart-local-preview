# SPDX-FileCopyrightText: 2026 GARDENA GmbH
#
# SPDX-License-Identifier: Apache-2.0

"""GARDENA smart SILENO mower entity."""

from __future__ import annotations

import logging
from functools import partial

import voluptuous as vol
from gardena_smart_local_api.devices import Device, MowerState
from homeassistant.components.lawn_mower import (
    LawnMowerActivity,
    LawnMowerEntity,
    LawnMowerEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_platform
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import GardenaSmartLocalCoordinator
from .entity import (
    EntityFactories,
    GardenaEntity,
    async_setup_device_entities,
    get_mower_duration_hours,
)

_LOGGER = logging.getLogger(__name__)

# Actions send commands to the gateway's local websocket — cap at 1 so HA
# serializes them instead of firing concurrent commands at the same connection
PARALLEL_UPDATES = 1


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator: GardenaSmartLocalCoordinator = entry.runtime_data

    platform = entity_platform.async_get_current_platform()
    platform.async_register_entity_service(
        "start_mowing",
        {
            # Whole hours, matching the Default Mowing Duration number entity
            # and the range the GARDENA app offers for a manual start.
            vol.Optional("duration"): vol.All(vol.Coerce(int), vol.Range(min=1, max=6))
        },
        "async_start_mowing_for",
    )

    def _entities_for_device(device: Device) -> EntityFactories:
        entities: EntityFactories = {}
        if hasattr(device, "build_start_mowing_obj"):
            entities["mower"] = partial(GardenaMower, coordinator, entry, device)
        return entities

    async_setup_device_entities(
        entry, coordinator, async_add_entities, _entities_for_device
    )


class GardenaMower(GardenaEntity, LawnMowerEntity):
    def __init__(
        self,
        coordinator: GardenaSmartLocalCoordinator,
        entry: ConfigEntry,
        device: Device,
    ) -> None:
        super().__init__(coordinator, device)
        self._entry = entry
        self._attr_unique_id = f"{device.id}_lawn_mower"
        self._attr_name = None
        self._attr_reports_position = False
        self._attr_supported_features = (
            LawnMowerEntityFeature.DOCK | LawnMowerEntityFeature.START_MOWING
        )
        if hasattr(device, "build_pause_mowing_obj"):
            self._attr_supported_features |= LawnMowerEntityFeature.PAUSE

    @property
    def activity(self) -> LawnMowerActivity | None:
        device = self.coordinator.data.get(self._device.id)
        if device is None:
            return None
        mower_state = device.state
        _LOGGER.debug("Mower status: %s", mower_state)
        match mower_state:
            case MowerState.CHARGING | MowerState.PARKED:
                return LawnMowerActivity.DOCKED

            case MowerState.LEAVING | MowerState.MOWING:
                return LawnMowerActivity.MOWING

            case MowerState.PAUSED:
                return LawnMowerActivity.PAUSED

            case MowerState.RETURNING:
                return LawnMowerActivity.RETURNING

            case MowerState.ERROR:
                return LawnMowerActivity.ERROR

        # MowerState.UNKNOWN or any state the dependency doesn't map yet.
        return None

    async def async_start_mowing(self) -> None:
        await self.async_start_mowing_for()

    async def async_start_mowing_for(self, duration: int | None = None) -> None:
        hours = (
            duration
            if duration is not None
            else get_mower_duration_hours(self._entry, self._device.id)
        )
        await self._send_confirmed_command(
            self._device.build_start_mowing_obj(hours * 3600)
        )
        _LOGGER.info("Start mowing with %s for %s hours", self._device.id, hours)

    async def async_dock(self) -> None:
        await self._send_confirmed_command(self._device.build_stop_mowing_obj())
        _LOGGER.info("Stop mowing with %s", self._device.id)

    async def async_pause(self) -> None:
        if hasattr(self._device, "build_pause_mowing_obj"):
            await self._send_confirmed_command(self._device.build_pause_mowing_obj())
            _LOGGER.info("Pause mowing with %s", self._device.id)
        else:
            _LOGGER.warning("Pause not supported for device %s", self._device.id)
