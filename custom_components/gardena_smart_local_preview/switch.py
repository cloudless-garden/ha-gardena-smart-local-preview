from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import GardenaSmartLocalCoordinator
from gardena_smart_local_api.devices import PowerAdapter

_LOGGER = logging.getLogger(__name__)

# used as "indefinitly" in the official app
DEFAULT_ON_DURATION_SECONDS = 16777216


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
            if isinstance(device, PowerAdapter) and device.id not in known_devices:
                known_devices.add(device.id)
                new_entities.append(GardenaPowerSwitch(coordinator, device))
                _LOGGER.info("Adding new switch entity for device %s", device.id)
        if new_entities:
            async_add_entities(new_entities)

    coordinator.async_add_listener(_add_new_devices)


class GardenaPowerSwitch(CoordinatorEntity[GardenaSmartLocalCoordinator], SwitchEntity):
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: GardenaSmartLocalCoordinator,
        device: PowerAdapter,
    ) -> None:
        super().__init__(coordinator)
        self._device = device
        self._attr_unique_id = f"{device.id}_switch"
        self._attr_name = None

        self._attr_device_info = dr.DeviceInfo(
            identifiers={(DOMAIN, device.id)},
            name=f"GARDENA {device.model_definition.name} {device.serial_number}",
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
    def is_on(self) -> bool | None:
        device = self.coordinator.data.get(self._device.id)
        if not device:
            return None
        return device.is_output_enabled

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.coordinator.send_request(
            self._device.id,
            self._device.build_enable_output_obj(DEFAULT_ON_DURATION_SECONDS),
        )
        _LOGGER.info("Turning on switch %s", self._device.id)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.coordinator.send_request(
            self._device.id,
            self._device.build_disable_output_obj(),
        )
        _LOGGER.info("Turning off switch %s", self._device.id)
