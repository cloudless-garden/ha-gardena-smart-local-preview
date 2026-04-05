from __future__ import annotations

import logging

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import GardenaSmartLocalCoordinator
from gardena_smart_local_api.devices.device import Device

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
                hasattr(device, "build_set_button_config_time_obj")
                and device.id not in known_devices
            ):
                known_devices.add(device.id)
                new_entities.append(GardenaButtonConfigTime(coordinator, device))
                _LOGGER.info(
                    "Adding new button config time entity for device %s", device.id
                )
        if new_entities:
            async_add_entities(new_entities)

    coordinator.async_add_listener(_add_new_devices)


class GardenaButtonConfigTime(
    CoordinatorEntity[GardenaSmartLocalCoordinator], NumberEntity
):
    _attr_has_entity_name = True
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
    ) -> None:
        super().__init__(coordinator)
        self._device = device
        self._attr_unique_id = f"{device.id}_button_config_time"
        self._attr_name = "Button Time"
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
    def native_value(self) -> float | None:
        device = self.coordinator.data.get(self._device.id)
        if not device:
            return None
        seconds = device.button_config_time
        if seconds is None:
            return None
        return int(round(seconds / 60))

    async def async_set_native_value(self, value: float) -> None:
        await self.coordinator.send_request(
            self._device.id,
            self._device.build_set_button_config_time_obj(int(value) * 60),
        )
        _LOGGER.info(
            "Set button config time for device %s to %s minutes",
            self._device.id,
            int(value),
        )
