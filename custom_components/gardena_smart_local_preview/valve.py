from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.valve import ValveEntity, ValveEntityFeature
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import GardenaSmartLocalCoordinator
from .entity import GardenaEntity
from gardena_smart_local_api.devices import Gen1WaterControl

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
            if isinstance(device, Gen1WaterControl) and device.id not in known_devices:
                known_devices.add(device.id)
                new_entities.append(GardenaValve(coordinator, device))
                _LOGGER.info("Adding new valve entity for device %s", device.id)
        if new_entities:
            async_add_entities(new_entities)

    coordinator.async_add_listener(_add_new_devices)


class GardenaValve(GardenaEntity, ValveEntity):
    def __init__(
        self,
        coordinator: GardenaSmartLocalCoordinator,
        device: Gen1WaterControl,
    ) -> None:
        super().__init__(coordinator, device)
        self._attr_unique_id = f"{device.id}_valve"
        self._attr_name = None
        self._attr_reports_position = False
        self._attr_supported_features = (
            ValveEntityFeature.OPEN | ValveEntityFeature.CLOSE
        )

    @property
    def is_closed(self) -> bool | None:
        device = self.coordinator.data.get(self._device.id)
        if not device:
            return None
        watering_timer = device.watering_timer
        is_opened = device.is_opened
        _LOGGER.debug(
            "Valve %s watering_timer=%s, is_opened=%s, returning is_closed=%s",
            self._device.id,
            watering_timer,
            is_opened,
            not is_opened,
        )
        return not is_opened

    async def async_open_valve(self, **kwargs: Any) -> None:
        await self.coordinator.send_request(
            self._device.id,
            self._device.build_set_watering_timer_obj(1800),
        )
        _LOGGER.info("Opening valve %s", self._device.id)

    async def async_close_valve(self, **kwargs: Any) -> None:
        await self.coordinator.send_request(
            self._device.id,
            self._device.build_stop_watering_obj(),
        )
        _LOGGER.info("Closing valve %s", self._device.id)
