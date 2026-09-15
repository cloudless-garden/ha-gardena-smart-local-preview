# SPDX-FileCopyrightText: 2026 GARDENA GmbH
#
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import logging
from functools import partial

from gardena_smart_local_api.devices import Pump
from gardena_smart_local_api.devices.device import Device
from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import GardenaSmartLocalCoordinator
from .entity import EntityFactories, GardenaEntity, async_setup_device_entities

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

    def _entities_for_device(device: Device) -> EntityFactories:
        entities: EntityFactories = {}
        if hasattr(device, "build_identify_obj"):
            entities["identify"] = partial(GardenaIdentifyButton, coordinator, device)
        if isinstance(device, Pump):
            entities["reset_flow"] = partial(
                GardenaPumpResetFlowButton, coordinator, device
            )
            entities["reset_valve_errors"] = partial(
                GardenaPumpResetValveErrorsButton, coordinator, device
            )
            entities["reset_temperature_min_max"] = partial(
                GardenaPumpResetTemperatureMinMaxButton, coordinator, device
            )
        if hasattr(device, "schedule_count"):
            entities["clear_schedules"] = partial(
                GardenaClearSchedulesButton, coordinator, device
            )
        return entities

    async_setup_device_entities(
        entry, coordinator, async_add_entities, _entities_for_device
    )


class GardenaIdentifyButton(GardenaEntity, ButtonEntity):
    def __init__(
        self, coordinator: GardenaSmartLocalCoordinator, device: Device
    ) -> None:
        super().__init__(coordinator, device)
        self._attr_unique_id = f"{device.id}_identify"
        self._attr_translation_key = "identify"
        self._attr_icon = "mdi:crosshairs-gps"
        self._attr_entity_category = EntityCategory.DIAGNOSTIC

    async def async_press(self) -> None:
        await self._send_confirmed_command(self._device.build_identify_obj())
        _LOGGER.info("Sent identify request for device %s", self._device.id)


class GardenaPumpResetFlowButton(GardenaEntity, ButtonEntity):
    def __init__(self, coordinator: GardenaSmartLocalCoordinator, device: Pump) -> None:
        super().__init__(coordinator, device)
        self._attr_unique_id = f"{device.id}_reset_flow"
        self._attr_translation_key = "reset_resettable_flow"
        self._attr_entity_category = EntityCategory.CONFIG

    async def async_press(self) -> None:
        await self._send_confirmed_command(
            self._device.build_reset_flow_resettable_obj()
        )
        _LOGGER.info("Reset resettable flow for device %s", self._device.id)


class GardenaPumpResetValveErrorsButton(GardenaEntity, ButtonEntity):
    def __init__(self, coordinator: GardenaSmartLocalCoordinator, device: Pump) -> None:
        super().__init__(coordinator, device)
        self._attr_unique_id = f"{device.id}_reset_valve_errors"
        self._attr_translation_key = "reset_valve_errors"
        self._attr_entity_category = EntityCategory.CONFIG

    async def async_press(self) -> None:
        await self._send_confirmed_command(
            self._device.build_reset_all_valve_errors_obj()
        )
        _LOGGER.info("Reset valve errors for device %s", self._device.id)


class GardenaPumpResetTemperatureMinMaxButton(GardenaEntity, ButtonEntity):
    def __init__(self, coordinator: GardenaSmartLocalCoordinator, device: Pump) -> None:
        super().__init__(coordinator, device)
        self._attr_unique_id = f"{device.id}_reset_temperature_min_max"
        self._attr_translation_key = "reset_temperature_min_max"
        self._attr_entity_category = EntityCategory.CONFIG

    async def async_press(self) -> None:
        await self._send_confirmed_command(
            self._device.build_reset_outlet_temperature_min_max_obj()
        )
        _LOGGER.info("Reset temperature min/max for device %s", self._device.id)


class GardenaClearSchedulesButton(GardenaEntity, ButtonEntity):
    _attr_entity_category = EntityCategory.CONFIG
    _attr_entity_registry_enabled_default = False
    _attr_translation_key = "clear_schedules"
    _attr_icon = "mdi:delete-alert-outline"

    def __init__(
        self, coordinator: GardenaSmartLocalCoordinator, device: Device
    ) -> None:
        super().__init__(coordinator, device)
        self._attr_unique_id = f"{device.id}_clear_schedules"

    async def async_press(self) -> None:
        await self._send_confirmed_command(self._device.build_clear_schedules_obj())
        _LOGGER.info("Cleared schedules for device %s", self._device.id)
