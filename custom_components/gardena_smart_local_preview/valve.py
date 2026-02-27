from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.valve import ValveEntity, ValveEntityFeature
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import GardenaSmartLocalCoordinator
from gardena_smart_local_api.devices import WaterControl

_LOGGER = logging.getLogger(__name__)


async def async_setup_platform(
    hass: HomeAssistant,
    config: dict,
    async_add_entities: AddEntitiesCallback,
    discovery_info: dict | None = None,
) -> None:
    coordinator: GardenaSmartLocalCoordinator = hass.data[DOMAIN]["yaml"]
    known_devices: set[str] = set()

    def _add_new_devices() -> None:
        if not coordinator.data:
            return
        new_entities = []
        for device in coordinator.data.values():
            if isinstance(device, WaterControl) and device.id not in known_devices:
                known_devices.add(device.id)
                new_entities.append(GardenaValve(coordinator, device))
                _LOGGER.info("Adding new valve entity for device %s", device.id)
        if new_entities:
            async_add_entities(new_entities)

    coordinator.async_add_listener(_add_new_devices)


class GardenaValve(CoordinatorEntity[GardenaSmartLocalCoordinator], ValveEntity):
    def __init__(
        self,
        coordinator: GardenaSmartLocalCoordinator,
        device: WaterControl,
    ) -> None:
        super().__init__(coordinator)
        self._device = device
        self._attr_unique_id = f"{device.id}_valve"
        self._attr_name = f"{device.manufacturer} {device.model_definition.name}"
        self._attr_reports_position = False
        self._attr_supported_features = (
            ValveEntityFeature.OPEN | ValveEntityFeature.CLOSE
        )

        self._attr_device_info = dr.DeviceInfo(
            identifiers={(DOMAIN, device.id)},
            name=f"{device.manufacturer} {device.model_definition.name}",
            manufacturer=device.manufacturer,
            model=device.model_definition.name,
            model_id=device.model_definition.model_number,
            sw_version=device.software_version,
            hw_version=device.hardware_version,
            serial_number=device.serial_number,
        )

    @property
    def available(self) -> bool:
        device = self.coordinator.data.get(self._device.id)
        if not device:
            return False
        return device.is_online

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
