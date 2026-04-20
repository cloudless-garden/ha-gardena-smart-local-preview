"""GARDENA smart SILENO mower entity."""

from __future__ import annotations

import logging

from gardena_smart_local_api.devices import (
    Gen1Mower1,
    Gen1Mower2,
    Gen1MowerStatus,
)

from homeassistant.components.lawn_mower import (
    LawnMowerActivity,
    LawnMowerEntity,
    LawnMowerEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import DOMAIN
from .coordinator import GardenaSmartLocalCoordinator
from .entity import GardenaEntity, find_device_subentry_id

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator: GardenaSmartLocalCoordinator = hass.data[DOMAIN][entry.entry_id]
    known_devices: set[str] = set()

    def _add_new_devices() -> None:
        if not coordinator.data:
            return
        known_devices.intersection_update(coordinator.data)
        entities_by_subentry_id: dict[str | None, list] = {}
        for device in coordinator.data.values():
            if (
                isinstance(device, (Gen1Mower1, Gen1Mower2))
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
        device: Gen1Mower1 | Gen1Mower2,
    ) -> None:
        super().__init__(coordinator, device)
        self._attr_unique_id = f"{device.id}_lawn_mower"
        self._attr_name = None
        self._attr_reports_position = False
        self._attr_supported_features = (
            LawnMowerEntityFeature.DOCK | LawnMowerEntityFeature.START_MOWING
        )

    @property
    def activity(self) -> LawnMowerActivity:
        status = self._device.status
        _LOGGER.debug("Mower status: %s", status)
        match status:
            case (
                Gen1MowerStatus.PAUSED
                | Gen1MowerStatus.OK_CHARGING
                | Gen1MowerStatus.PARKED_WEEK_TIMER
                | Gen1MowerStatus.PARKED_BY_USER
                | Gen1MowerStatus.PARKED_AUTOTIMER
                | Gen1MowerStatus.PARKED_DAY_LIMIT
                | Gen1MowerStatus.PARKED_FROST
                | Gen1MowerStatus.WAIT_POWER_UP
                | Gen1MowerStatus.OFF_MAIN_SWITCH
                | Gen1MowerStatus.WAIT
            ):
                return LawnMowerActivity.DOCKED
            case (
                Gen1MowerStatus.OK_LEAVING_CS
                | Gen1MowerStatus.OK_CUTTING_AUTO
                | Gen1MowerStatus.OK_CUTTING_MANUAL
            ):
                return LawnMowerActivity.MOWING
            case Gen1MowerStatus.OK_SEARCHING_CS:
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
