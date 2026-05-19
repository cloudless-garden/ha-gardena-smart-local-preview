from __future__ import annotations

import logging

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import LIGHT_LUX, PERCENTAGE, EntityCategory, UnitOfTemperature, UnitOfTime, UnitOfLength
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import GardenaSmartLocalCoordinator
from .entity import GardenaEntity
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
    known_charging_cycles_devices: set[str] = set()
    known_cutting_time_devices: set[str] = set()
    known_running_time_devices: set[str] = set()
    known_collisions_devices: set[str] = set()
    known_rf_link_devices: set[str] = set()
    known_guide_wire_length_devices: set[str] = set()

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
                hasattr(device, "charging_cycles")
                and device.id not in known_charging_cycles_devices
            ):
                known_charging_cycles_devices.add(device.id)
                new_entities.append(GardenaChargingCyclesSensor(coordinator, device))
                _LOGGER.info(
                    "Adding new charging cycles sensor entity for device %s", device.id
                )
            if (
                hasattr(device, "cutting_time")
                and device.id not in known_cutting_time_devices
            ):
                known_cutting_time_devices.add(device.id)
                new_entities.append(GardenaCuttingTimeSensor(coordinator, device))
                _LOGGER.info(
                    "Adding new cutting time sensor entity for device %s", device.id
                )
            if (
                hasattr(device, "running_time")
                and device.id not in known_running_time_devices
            ):
                known_running_time_devices.add(device.id)
                new_entities.append(GardenaRunningTimeSensor(coordinator, device))
                _LOGGER.info(
                    "Adding new running time sensor entity for device %s", device.id
                )
            if (
                hasattr(device, "collisions")
                and device.id not in known_collisions_devices
            ):
                known_collisions_devices.add(device.id)
                new_entities.append(GardenaCollisionsSensor(coordinator, device))
                _LOGGER.info(
                    "Adding new collisions sensor entity for device %s", device.id
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
            if (
                hasattr(device, "guide_wire_length")
                and device.id not in known_guide_wire_length_devices
            ):
                known_guide_wire_length_devices.add(device.id)
                new_entities.append(GardenaGuideWireLengthSensor(coordinator, device))
                _LOGGER.info(
                    "Adding new guide wire length sensor entity for device %s", device.id
                )
        if new_entities:
            async_add_entities(new_entities)

    coordinator.async_add_listener(_add_new_devices)


class GardenaTemperatureSensor(GardenaEntity, SensorEntity):
    def __init__(
        self,
        coordinator: GardenaSmartLocalCoordinator,
        device: Device,
    ) -> None:
        super().__init__(coordinator, device)
        self._attr_unique_id = f"{device.id}_temperature"
        self._attr_name = "Temperature"
        self._attr_device_class = SensorDeviceClass.TEMPERATURE
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS

    @property
    def native_value(self) -> float | None:
        device = self.coordinator.data.get(self._device.id)
        if not device:
            return None
        temp = device.temperature
        return float(temp) if temp is not None else None


class GardenaSoilMoistureSensor(GardenaEntity, SensorEntity):
    def __init__(
        self,
        coordinator: GardenaSmartLocalCoordinator,
        device: Device,
    ) -> None:
        super().__init__(coordinator, device)
        self._attr_unique_id = f"{device.id}_soil_moisture"
        self._attr_name = "Soil Moisture"
        self._attr_device_class = SensorDeviceClass.MOISTURE
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_native_unit_of_measurement = PERCENTAGE

    @property
    def native_value(self) -> float | None:
        device = self.coordinator.data.get(self._device.id)
        if not device:
            return None
        moisture = device.soil_moisture
        return float(moisture) if moisture is not None else None


class GardenaLightSensor(GardenaEntity, SensorEntity):
    def __init__(
        self,
        coordinator: GardenaSmartLocalCoordinator,
        device: Device,
    ) -> None:
        super().__init__(coordinator, device)
        self._attr_unique_id = f"{device.id}_light"
        self._attr_name = "Light"
        self._attr_device_class = SensorDeviceClass.ILLUMINANCE
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_native_unit_of_measurement = LIGHT_LUX

    @property
    def native_value(self) -> float | None:
        device = self.coordinator.data.get(self._device.id)
        if not device:
            return None
        lux = device.light
        return float(lux) if lux is not None else None


class GardenaBatterySensor(GardenaEntity, SensorEntity):
    def __init__(
        self,
        coordinator: GardenaSmartLocalCoordinator,
        device: Device,
    ) -> None:
        super().__init__(coordinator, device)
        self._attr_unique_id = f"{device.id}_battery"
        self._attr_name = "Battery"
        self._attr_device_class = SensorDeviceClass.BATTERY
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_native_unit_of_measurement = PERCENTAGE

    @property
    def native_value(self) -> float | None:
        device = self.coordinator.data.get(self._device.id)
        if not device:
            return None
        level = device.battery_level
        return float(level) if level is not None else None


class GardenaChargingCyclesSensor(GardenaEntity, SensorEntity):
    def __init__(
        self,
        coordinator: GardenaSmartLocalCoordinator,
        device: Device,
    ) -> None:
        super().__init__(coordinator, device)
        self._attr_unique_id = f"{device.id}_charging_cycles"
        self._attr_name = "Charging Cycles"
        self._attr_icon = "mdi:counter"
        self._attr_state_class = SensorStateClass.MEASUREMENT
    
    @property
    def native_value(self) -> int | None:
        device = self.coordinator.data.get(self._device.id)
        if not device:
            return None
        return device.charging_cycles


class GardenaCuttingTimeSensor(GardenaEntity, SensorEntity):
    def __init__(
        self,
        coordinator: GardenaSmartLocalCoordinator,
        device: Device,
    ) -> None:
        super().__init__(coordinator, device)
        self._attr_unique_id = f"{device.id}_cutting_time"
        self._attr_name = "Cutting Time"
        self._attr_icon = "mdi:clock-outline"
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_native_unit_of_measurement = UnitOfTime.HOURS
    
    @property
    def native_value(self) -> int | None:
        device = self.coordinator.data.get(self._device.id)
        if not device:
            return None
        return device.cutting_time
    

class GardenaRunningTimeSensor(GardenaEntity, SensorEntity):
    def __init__(
        self,
        coordinator: GardenaSmartLocalCoordinator,
        device: Device,
    ) -> None:
        super().__init__(coordinator, device)
        self._attr_unique_id = f"{device.id}_running_time"
        self._attr_name = "Running Time"
        self._attr_icon = "mdi:clock-outline"
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_native_unit_of_measurement = UnitOfTime.HOURS
    
    @property
    def native_value(self) -> int | None:
        device = self.coordinator.data.get(self._device.id)
        if not device:
            return None
        return device.running_time


class GardenaCollisionsSensor(GardenaEntity, SensorEntity):
    def __init__(
        self,
        coordinator: GardenaSmartLocalCoordinator,
        device: Device,
    ) -> None:
        super().__init__(coordinator, device)
        self._attr_unique_id = f"{device.id}_collisions"
        self._attr_name = "Collisions"
        self._attr_icon = "mdi:counter"
        self._attr_state_class = SensorStateClass.MEASUREMENT
    
    @property
    def native_value(self) -> int | None:
        device = self.coordinator.data.get(self._device.id)
        if not device:
            return None
        return device.collisions
    

class GardenaRfLinkQualitySensor(GardenaEntity, SensorEntity):
    def __init__(
        self,
        coordinator: GardenaSmartLocalCoordinator,
        device: Device,
    ) -> None:
        super().__init__(coordinator, device)
        self._attr_unique_id = f"{device.id}_rf_link_quality"
        self._attr_name = "RF Link Quality"
        self._attr_icon = "mdi:signal"
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_native_unit_of_measurement = PERCENTAGE
        self._attr_entity_category = EntityCategory.DIAGNOSTIC

    @property
    def native_value(self) -> int | None:
        device = self.coordinator.data.get(self._device.id)
        if not device:
            return None
        return device.rf_link_quality


class GardenaGuideWireLengthSensor(GardenaEntity, SensorEntity):
    def __init__(
        self,
        coordinator: GardenaSmartLocalCoordinator,
        device: Device,
    ) -> None:
        super().__init__(coordinator, device)
        self._attr_unique_id = f"{device.id}_guide_wire_length"
        self._attr_name = "Guide Wire Length"
        self._attr_icon = "mdi:ruler"
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_native_unit_of_measurement = UnitOfLength.METERS
        self._attr_entity_category = EntityCategory.DIAGNOSTIC
    
    @property
    def native_value(self) -> int | None:
        device = self.coordinator.data.get(self._device.id)
        if not device:
            return None
        return device.guide_wire_length
