from __future__ import annotations

import logging

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature
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
            if hasattr(device, "temperature") and device.id not in known_devices:
                known_devices.add(device.id)
                new_entities.append(GardenaTemperatureSensor(coordinator, device))
                _LOGGER.info(
                    "Adding new temperature sensor entity for device %s", device.id
                )
        if new_entities:
            async_add_entities(new_entities)

    coordinator.async_add_listener(_add_new_devices)


class GardenaTemperatureSensor(
    CoordinatorEntity[GardenaSmartLocalCoordinator], SensorEntity
):
    def __init__(
        self,
        coordinator: GardenaSmartLocalCoordinator,
        device: Device,
    ) -> None:
        super().__init__(coordinator)
        self._device = device
        self._attr_unique_id = f"{device.id}_temperature"
        self._attr_name = f"GARDENA {device.model_definition.name} Temperature"
        self._attr_device_class = SensorDeviceClass.TEMPERATURE
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS

        self._attr_device_info = dr.DeviceInfo(
            identifiers={(DOMAIN, device.id)},
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
        temp = device.temperature
        return float(temp) if temp is not None else None
