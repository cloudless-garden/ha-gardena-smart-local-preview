# SPDX-FileCopyrightText: 2026 GARDENA GmbH
#
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import logging

from homeassistant.components.button import ButtonEntity
from homeassistant.const import EntityCategory
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import GardenaSmartLocalCoordinator
from .entity import GardenaEntity, find_device_subentry_id
from gardena_smart_local_api.devices.device import Device
from gardena_smart_local_api.devices import Pump

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
    known_devices: set[str] = set()
    known_pump_devices: set[str] = set()
    known_schedule_devices: set[str] = set()

    def _add_new_devices() -> None:
        if not coordinator.data:
            return
        known_devices.intersection_update(coordinator.data)
        known_pump_devices.intersection_update(coordinator.data)
        known_schedule_devices.intersection_update(coordinator.data)
        entities_by_subentry_id: dict[str | None, list] = {}
        for device in coordinator.data.values():
            if hasattr(device, "build_identify_obj") and device.id not in known_devices:
                known_devices.add(device.id)
                sid = find_device_subentry_id(entry, device.id)
                entities_by_subentry_id.setdefault(sid, []).append(
                    GardenaIdentifyButton(coordinator, device)
                )
                _LOGGER.info("Adding identify button for device %s", device.id)
            if isinstance(device, Pump) and device.id not in known_pump_devices:
                known_pump_devices.add(device.id)
                sid = find_device_subentry_id(entry, device.id)
                entities_by_subentry_id.setdefault(sid, []).extend(
                    [
                        GardenaPumpResetFlowButton(coordinator, device),
                        GardenaPumpResetValveErrorsButton(coordinator, device),
                        GardenaPumpResetTemperatureMinMaxButton(coordinator, device),
                    ]
                )
                _LOGGER.info("Adding pump reset buttons for device %s", device.id)
            if (
                hasattr(device, "schedule_count")
                and device.id not in known_schedule_devices
            ):
                known_schedule_devices.add(device.id)
                sid = find_device_subentry_id(entry, device.id)
                entities_by_subentry_id.setdefault(sid, []).append(
                    GardenaClearSchedulesButton(coordinator, device)
                )
                _LOGGER.info("Adding clear schedules button for device %s", device.id)
        for sid, entities in entities_by_subentry_id.items():
            async_add_entities(entities, config_subentry_id=sid)

    entry.async_on_unload(coordinator.async_add_listener(_add_new_devices))
    _add_new_devices()


class GardenaIdentifyButton(GardenaEntity, ButtonEntity):
    def __init__(
        self, coordinator: GardenaSmartLocalCoordinator, device: Device
    ) -> None:
        super().__init__(coordinator, device)
        self._attr_unique_id = f"{device.id}_identify"
        self._attr_name = "Identify"
        self._attr_icon = "mdi:crosshairs-gps"
        self._attr_entity_category = EntityCategory.DIAGNOSTIC

    async def async_press(self) -> None:
        await self.coordinator.send_request(
            self._device.id,
            self._device.build_identify_obj(),
        )
        _LOGGER.info("Sent identify request for device %s", self._device.id)


class GardenaPumpResetFlowButton(GardenaEntity, ButtonEntity):
    def __init__(self, coordinator: GardenaSmartLocalCoordinator, device: Pump) -> None:
        super().__init__(coordinator, device)
        self._attr_unique_id = f"{device.id}_reset_flow"
        self._attr_name = "Reset Resettable Flow"
        self._attr_entity_category = EntityCategory.CONFIG

    async def async_press(self) -> None:
        await self.coordinator.send_request(
            self._device.id,
            self._device.build_reset_flow_resettable_obj(),
        )
        _LOGGER.info("Reset resettable flow for device %s", self._device.id)


class GardenaPumpResetValveErrorsButton(GardenaEntity, ButtonEntity):
    def __init__(self, coordinator: GardenaSmartLocalCoordinator, device: Pump) -> None:
        super().__init__(coordinator, device)
        self._attr_unique_id = f"{device.id}_reset_valve_errors"
        self._attr_name = "Reset Valve Errors"
        self._attr_entity_category = EntityCategory.CONFIG

    async def async_press(self) -> None:
        await self.coordinator.send_request(
            self._device.id,
            self._device.build_reset_all_valve_errors_obj(),
        )
        _LOGGER.info("Reset valve errors for device %s", self._device.id)


class GardenaPumpResetTemperatureMinMaxButton(GardenaEntity, ButtonEntity):
    def __init__(self, coordinator: GardenaSmartLocalCoordinator, device: Pump) -> None:
        super().__init__(coordinator, device)
        self._attr_unique_id = f"{device.id}_reset_temperature_min_max"
        self._attr_name = "Reset Temperature Min/Max"
        self._attr_entity_category = EntityCategory.CONFIG

    async def async_press(self) -> None:
        await self.coordinator.send_request(
            self._device.id,
            self._device.build_reset_outlet_temperature_min_max_obj(),
        )
        _LOGGER.info("Reset temperature min/max for device %s", self._device.id)


class GardenaClearSchedulesButton(GardenaEntity, ButtonEntity):
    _attr_entity_category = EntityCategory.CONFIG
    _attr_entity_registry_enabled_default = False
    _attr_has_entity_name = True
    _attr_name = "Clear Schedules"
    _attr_icon = "mdi:delete-alert-outline"

    def __init__(
        self, coordinator: GardenaSmartLocalCoordinator, device: Device
    ) -> None:
        super().__init__(coordinator, device)
        self._attr_unique_id = f"{device.id}_clear_schedules"

    async def async_press(self) -> None:
        await self.coordinator.send_request(
            self._device.id,
            self._device.build_clear_schedules_obj(),
        )
        _LOGGER.info("Cleared schedules for device %s", self._device.id)
