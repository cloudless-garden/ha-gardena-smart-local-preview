# SPDX-FileCopyrightText: 2026 GARDENA GmbH
#
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import logging

from gardena_smart_local_api.devices import Pump
from gardena_smart_local_api.devices.device import Device
from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory, UnitOfPressure, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import DEFAULT_VALVE_DURATION_MINUTES
from .coordinator import GardenaSmartLocalCoordinator
from .entity import (
    GardenaEntity,
    async_set_valve_duration_minutes,
    find_device_subentry_id,
    get_valve_duration_minutes,
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
    known_devices: set[str] = set()
    known_button_time_valves: set[tuple[str, int]] = set()
    known_valves: set[tuple[str, int]] = set()

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

        current_valves: set[tuple[str, int]] = set()
        for device in coordinator.data.values():
            for valve_id in getattr(device, "valve_ids", []):
                current_valves.add((device.id, valve_id))
        known_valves.intersection_update(current_valves)

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

            new_valve_ids: list[int] = []
            for valve_id in getattr(device, "valve_ids", []):
                if (device.id, valve_id) not in known_valves:
                    new_valve_ids.append(valve_id)

            if new_valve_ids:
                sid = find_device_subentry_id(entry, device.id)
                for valve_id in new_valve_ids:
                    known_valves.add((device.id, valve_id))
                    entities_by_subentry_id.setdefault(sid, []).append(
                        GardenaValveDuration(coordinator, entry, device, valve_id)
                    )
                    _LOGGER.info(
                        "Adding new valve duration entity for device %s, valve %s, "
                        "default duration=%s minutes",
                        device.id,
                        valve_id,
                        DEFAULT_VALVE_DURATION_MINUTES,
                    )
        for sid, entities in entities_by_subentry_id.items():
            async_add_entities(entities, config_subentry_id=sid)

    entry.async_on_unload(coordinator.async_add_listener(_add_new_devices))
    _add_new_devices()


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
        if multi_valve:
            self._attr_name = f"Button Watering Duration {valve_id + 1}"
        else:
            self._attr_name = "Button Watering Duration"
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
        return round(seconds / 60)

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
            "Set button config time for device %s, valve %s to %s minutes",
            self._device.id,
            self._valve_id,
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


class GardenaValveDuration(GardenaEntity, NumberEntity):
    _attr_native_min_value = 1
    # Matches the ceiling the GARDENA app offers; how the firmware itself
    # handles the maximum is not validated yet.
    _attr_native_max_value = 180
    _attr_native_step = 1
    _attr_native_unit_of_measurement = UnitOfTime.MINUTES
    _attr_mode = NumberMode.BOX
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(
        self,
        coordinator: GardenaSmartLocalCoordinator,
        entry: ConfigEntry,
        device: Device,
        valve_id: int,
    ) -> None:
        super().__init__(coordinator, device)
        self._entry = entry
        self._valve_id = valve_id
        self._attr_unique_id = f"{device.id}_valve_{valve_id}_duration"
        self._attr_name = (
            f"Valve {valve_id + 1} Default Watering Duration"
            if len(device.valve_ids) > 1
            else "Default Watering Duration"
        )
        self._attr_icon = "mdi:timer-outline"

    # Stored in the config subentry rather than read from the device, so it
    # stays settable while the gateway or the device itself is unreachable.
    @property
    def available(self) -> bool:
        return True

    @property
    def native_value(self) -> float | None:
        return get_valve_duration_minutes(self._entry, self._device.id, self._valve_id)

    async def async_set_native_value(self, value: float) -> None:
        minutes = int(value)
        async_set_valve_duration_minutes(
            self.hass, self._entry, self._device.id, self._valve_id, minutes
        )
        self.async_write_ha_state()
        _LOGGER.info(
            "Set valve duration for device %s valve_id=%s to %s minutes",
            self._device.id,
            self._valve_id,
            minutes,
        )
