# SPDX-FileCopyrightText: 2026 GARDENA GmbH
#
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import logging

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory, UnitOfTime, UnitOfPressure
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
    known_button_time_valves: set[tuple[str, int]] = set()

    def _add_new_devices() -> None:
        if not coordinator.data:
            return
        known_devices.intersection_update(coordinator.data)
        known_button_time_valves.intersection_update(
            (device.id, valve_id)
            for device in coordinator.data.values()
            if hasattr(device, "build_set_button_config_time_obj")
            for valve_id in device.valve_ids
        )
        entities_by_subentry_id: dict[str | None, list] = {}
        for device in coordinator.data.values():
            if hasattr(device, "build_set_button_config_time_obj"):
                sid = find_device_subentry_id(entry, device.id)
                for valve_id in device.valve_ids:
                    key = (device.id, valve_id)
                    if key in known_button_time_valves:
                        continue
                    known_button_time_valves.add(key)
                    entities_by_subentry_id.setdefault(sid, []).append(
                        GardenaButtonConfigTime(coordinator, device, valve_id)
                    )
                    _LOGGER.info(
                        "Adding new button config time entity for device %s, valve %s",
                        device.id,
                        valve_id,
                    )
            elif isinstance(device, Pump) and device.id not in known_devices:
                known_devices.add(device.id)
                sid = find_device_subentry_id(entry, device.id)
                entities_by_subentry_id.setdefault(sid, []).extend(
                    [
                        GardenaPumpTurnOnPressure(coordinator, device),
                        GardenaPumpDrippingAlert(coordinator, device),
                    ]
                )
                _LOGGER.info("Adding new pump number entities for device %s", device.id)
        for sid, entities in entities_by_subentry_id.items():
            async_add_entities(entities, config_subentry_id=sid)

    coordinator.async_add_listener(_add_new_devices)


class GardenaButtonConfigTime(GardenaEntity, NumberEntity):
    _attr_native_min_value = 0
    _attr_native_max_value = 90
    _attr_native_step = 1
    _attr_native_unit_of_measurement = UnitOfTime.MINUTES
    _attr_mode = NumberMode.BOX
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(
        self,
        coordinator: GardenaSmartLocalCoordinator,
        device: Device,
        valve_id: int = 0,
    ) -> None:
        super().__init__(coordinator, device)
        self._valve_id = valve_id
        multi_valve = len(device.valve_ids) > 1
        suffix = f"_{valve_id}" if multi_valve else ""
        self._attr_unique_id = f"{device.id}_button_config_time{suffix}"
        self._attr_name = (
            f"Button Time {valve_id + 1}" if multi_valve else "Button Time"
        )
        self._attr_icon = "mdi:timer-outline"

    @property
    def native_value(self) -> float | None:
        device = self.coordinator.data.get(self._device.id)
        if not device:
            return None
        if hasattr(device, "get_button_config_time"):
            seconds = device.get_button_config_time(self._valve_id)
        else:
            seconds = device.button_config_time
        if seconds is None:
            return None
        return int(round(seconds / 60))

    async def async_set_native_value(self, value: float) -> None:
        seconds = int(value) * 60
        if hasattr(self._device, "get_button_config_time"):
            request = self._device.build_set_button_config_time_obj(
                seconds, self._valve_id
            )
        else:
            request = self._device.build_set_button_config_time_obj(seconds)
        await self.coordinator.send_request(self._device.id, request)
        _LOGGER.info(
            "Set button config time for device %s to %s minutes",
            self._device.id,
            int(value),
        )


class GardenaPumpTurnOnPressure(GardenaEntity, NumberEntity):
    _attr_native_min_value = 0.0
    _attr_native_max_value = 10.0
    _attr_native_step = 0.1
    _attr_native_unit_of_measurement = UnitOfPressure.BAR
    _attr_mode = NumberMode.BOX
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(
        self,
        coordinator: GardenaSmartLocalCoordinator,
        device: Pump,
    ) -> None:
        super().__init__(coordinator, device)
        self._attr_unique_id = f"{device.id}_turn_on_pressure"
        self._attr_name = "Turn-On Pressure"

    @property
    def native_value(self) -> float | None:
        device = self.coordinator.data.get(self._device.id)
        if not device:
            return None
        return device.turn_on_pressure

    async def async_set_native_value(self, value: float) -> None:
        await self.coordinator.send_request(
            self._device.id,
            self._device.build_set_turn_on_pressure_obj(value),
        )
        _LOGGER.info(
            "Set turn-on pressure for device %s to %s bar",
            self._device.id,
            value,
        )


class GardenaPumpDrippingAlert(GardenaEntity, NumberEntity):
    _attr_native_min_value = 0
    _attr_native_max_value = 3600
    _attr_native_step = 1
    _attr_native_unit_of_measurement = UnitOfTime.SECONDS
    _attr_mode = NumberMode.BOX
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(
        self,
        coordinator: GardenaSmartLocalCoordinator,
        device: Pump,
    ) -> None:
        super().__init__(coordinator, device)
        self._attr_unique_id = f"{device.id}_dripping_alert"
        self._attr_name = "Dripping Alert Timeout"

    @property
    def native_value(self) -> float | None:
        device = self.coordinator.data.get(self._device.id)
        if not device:
            return None
        return device.dripping_alert

    async def async_set_native_value(self, value: float) -> None:
        await self.coordinator.send_request(
            self._device.id,
            self._device.build_set_dripping_alert_obj(int(value)),
        )
        _LOGGER.info(
            "Set dripping alert timeout for device %s to %s seconds",
            self._device.id,
            int(value),
        )
