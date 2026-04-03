from __future__ import annotations

import logging

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import LIGHT_LUX, PERCENTAGE, EntityCategory, UnitOfTemperature
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
    known_temp_devices: set[str] = set()
    known_moisture_devices: set[str] = set()
    known_light_devices: set[str] = set()
    known_battery_devices: set[str] = set()
    known_rf_link_devices: set[str] = set()

    def _add_new_devices() -> None:
        if not coordinator.data:
            return
        new_entities = []
        for device in coordinator.data.values():
            if hasattr(device, "temperature") and device.id not in known_temp_devices:
                known_temp_devices.add(device.id)
                new_entities.append(GardenaTemperatureSensor(coordinator, device))
                _LOGGER.info(
                    "Adding new temperature sensor entity for device %s", device.id
                )
            if (
                hasattr(device, "soil_moisture")
                and device.id not in known_moisture_devices
            ):
                known_moisture_devices.add(device.id)
                new_entities.append(GardenaSoilMoistureSensor(coordinator, device))
                _LOGGER.info(
                    "Adding new soil moisture sensor entity for device %s", device.id
                )
            if hasattr(device, "light") and device.id not in known_light_devices:
                known_light_devices.add(device.id)
                new_entities.append(GardenaLightSensor(coordinator, device))
                _LOGGER.info("Adding new light sensor entity for device %s", device.id)
            if (
                hasattr(device, "battery_level")
                and device.id not in known_battery_devices
            ):
                known_battery_devices.add(device.id)
                new_entities.append(GardenaBatterySensor(coordinator, device))
                _LOGGER.info(
                    "Adding new battery sensor entity for device %s", device.id
                )
            if (
                hasattr(device, "rf_link_quality")
                and device.id not in known_rf_link_devices
            ):
                known_rf_link_devices.add(device.id)
                new_entities.append(GardenaRfLinkQualitySensor(coordinator, device))
                _LOGGER.info(
                    "Adding new RF link quality sensor entity for device %s", device.id
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


class GardenaSoilMoistureSensor(
    CoordinatorEntity[GardenaSmartLocalCoordinator], SensorEntity
):
    def __init__(
        self,
        coordinator: GardenaSmartLocalCoordinator,
        device: Device,
    ) -> None:
        super().__init__(coordinator)
        self._device = device
        self._attr_unique_id = f"{device.id}_soil_moisture"
        self._attr_name = (
            f"{device.manufacturer} {device.model_definition.name} Soil Moisture"
        )
        self._attr_device_class = SensorDeviceClass.MOISTURE
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_native_unit_of_measurement = PERCENTAGE

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
        moisture = device.soil_moisture
        return float(moisture) if moisture is not None else None


class GardenaLightSensor(CoordinatorEntity[GardenaSmartLocalCoordinator], SensorEntity):
    def __init__(
        self,
        coordinator: GardenaSmartLocalCoordinator,
        device: Device,
    ) -> None:
        super().__init__(coordinator)
        self._device = device
        self._attr_unique_id = f"{device.id}_light"
        self._attr_name = f"{device.manufacturer} {device.model_definition.name} Light"
        self._attr_device_class = SensorDeviceClass.ILLUMINANCE
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_native_unit_of_measurement = LIGHT_LUX

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
        lux = device.light
        return float(lux) if lux is not None else None


class GardenaBatterySensor(
    CoordinatorEntity[GardenaSmartLocalCoordinator], SensorEntity
):
    def __init__(
        self,
        coordinator: GardenaSmartLocalCoordinator,
        device: Device,
    ) -> None:
        super().__init__(coordinator)
        self._device = device
        self._attr_unique_id = f"{device.id}_battery"
        self._attr_name = (
            f"{device.manufacturer} {device.model_definition.name} Battery"
        )
        self._attr_device_class = SensorDeviceClass.BATTERY
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_native_unit_of_measurement = PERCENTAGE

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
        level = device.battery_level
        return float(level) if level is not None else None


class GardenaRfLinkQualitySensor(
    CoordinatorEntity[GardenaSmartLocalCoordinator], SensorEntity
):
    def __init__(
        self,
        coordinator: GardenaSmartLocalCoordinator,
        device: Device,
    ) -> None:
        super().__init__(coordinator)
        self._device = device
        self._attr_unique_id = f"{device.id}_rf_link_quality"
        self._attr_name = (
            f"{device.manufacturer} {device.model_definition.name} RF Link Quality"
        )
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_native_unit_of_measurement = PERCENTAGE
        self._attr_entity_category = EntityCategory.DIAGNOSTIC

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
    def native_value(self) -> int | None:
        device = self.coordinator.data.get(self._device.id)
        if not device:
            return None
        return device.rf_link_quality
