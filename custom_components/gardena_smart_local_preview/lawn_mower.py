"""GARDENA smart SILENO mower entity."""

from __future__ import annotations

import logging

from gardena_smart_local_api.devices import (
    Gen1Mower1,
    Gen1Mower2,
    MowerState,
)

from homeassistant.components.lawn_mower import (
    LawnMowerActivity,
    LawnMowerEntity,
    LawnMowerEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import GardenaSmartLocalCoordinator
from .entity import GardenaEntity

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: GardenaSmartLocalCoordinator = hass.data[DOMAIN][entry.entry_id]
    known_devices: set[str] = set()

    def _add_new_devices() -> None:
        if not coordinator.data:
            return
        new_entities = []
        for device in coordinator.data.values():
            if (
                isinstance(device, (Gen1Mower1, Gen1Mower2))
                and device.id not in known_devices
            ):
                known_devices.add(device.id)
                new_entities.append(GardenaMower(coordinator, device))
                _LOGGER.info("Adding new mower entity for device %s", device.id)
        if new_entities:
            async_add_entities(new_entities)

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
        mower_state = self._device.state
        _LOGGER.debug("Mower status: %s", mower_state)
        match mower_state:
            case MowerState.PARKED:
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
