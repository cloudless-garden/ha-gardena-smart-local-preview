# SPDX-FileCopyrightText: 2026 GARDENA GmbH
#
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from functools import partial
from typing import Any, ClassVar

from gardena_smart_local_api.devices import Pump
from gardena_smart_local_api.devices.device import Device, FirmwareUpdateState
from gardena_smart_local_api.devices.irrigation import PumpState
from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    LIGHT_LUX,
    PERCENTAGE,
    EntityCategory,
    UnitOfPressure,
    UnitOfTemperature,
    UnitOfTime,
    UnitOfVolume,
    UnitOfVolumeFlowRate,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import mower as mower_helpers
from .coordinator import GardenaSmartLocalCoordinator
from .entity import EntityFactories, GardenaEntity, async_setup_device_entities

# State comes only from the coordinator's push (no polling, no actions) —
# there is nothing here for PARALLEL_UPDATES to throttle
PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator: GardenaSmartLocalCoordinator = entry.runtime_data

    def _entities_for_device(device: Device) -> EntityFactories:
        entities: EntityFactories = {}
        if hasattr(device, "temperature"):
            entities["temperature"] = partial(
                GardenaTemperatureSensor, coordinator, device
            )
        if hasattr(device, "soil_moisture"):
            entities["soil_moisture"] = partial(
                GardenaSoilMoistureSensor, coordinator, device
            )
        if hasattr(device, "light"):
            entities["light"] = partial(GardenaLightSensor, coordinator, device)
        if hasattr(device, "battery_level"):
            entities["battery"] = partial(GardenaBatterySensor, coordinator, device)
        if hasattr(device, "rf_link_quality"):
            entities["rf_link_quality"] = partial(
                GardenaRfLinkQualitySensor, coordinator, device
            )
        if mower_helpers.is_gen1_mower(device):
            entities["last_error"] = partial(
                GardenaMowerLastErrorSensor, coordinator, device
            )
            for description in MOWER_STATISTICS:
                entities[description.key] = partial(
                    GardenaMowerStatisticSensor, coordinator, device, description
                )
        if isinstance(device, Pump):
            entities["pump_pressure"] = partial(
                GardenaPumpPressureSensor, coordinator, device
            )
            entities["pump_temperature"] = partial(
                GardenaPumpTemperatureSensor, coordinator, device
            )
            entities["pump_flow_rate"] = partial(
                GardenaPumpFlowRateSensor, coordinator, device
            )
            entities["pump_flow_total"] = partial(
                GardenaPumpFlowTotalSensor, coordinator, device
            )
            entities["pump_flow_since_reset"] = partial(
                GardenaPumpFlowSinceResetSensor, coordinator, device
            )
            entities["pump_state"] = partial(
                GardenaPumpStateSensor, coordinator, device
            )
        if hasattr(device, "schedule_count"):
            entities["schedule_count"] = partial(
                GardenaScheduleCountSensor, coordinator, device
            )
        entities["firmware_update_state"] = partial(
            GardenaFirmwareUpdateStateSensor, coordinator, device
        )
        return entities

    async_setup_device_entities(
        entry, coordinator, async_add_entities, _entities_for_device
    )


class GardenaTemperatureSensor(GardenaEntity, SensorEntity):
    def __init__(
        self,
        coordinator: GardenaSmartLocalCoordinator,
        device: Device,
    ) -> None:
        super().__init__(coordinator, device)
        self._attr_unique_id = f"{device.id}_temperature"
        self._attr_translation_key = "temperature"
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
        self._attr_translation_key = "soil_moisture"
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
        self._attr_translation_key = "light"
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
        self._attr_translation_key = "battery"
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


class GardenaRfLinkQualitySensor(GardenaEntity, SensorEntity):
    def __init__(
        self,
        coordinator: GardenaSmartLocalCoordinator,
        device: Device,
    ) -> None:
        super().__init__(coordinator, device)
        self._attr_unique_id = f"{device.id}_rf_link_quality"
        self._attr_translation_key = "rf_link_quality"
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


class GardenaPumpPressureSensor(GardenaEntity, SensorEntity):
    def __init__(
        self,
        coordinator: GardenaSmartLocalCoordinator,
        device: Pump,
    ) -> None:
        super().__init__(coordinator, device)
        self._attr_unique_id = f"{device.id}_outlet_pressure"
        self._attr_translation_key = "outlet_pressure"
        self._attr_device_class = SensorDeviceClass.PRESSURE
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_native_unit_of_measurement = UnitOfPressure.BAR

    @property
    def native_value(self) -> float | None:
        device = self.coordinator.data.get(self._device.id)
        if not device:
            return None
        return device.outlet_pressure


class GardenaPumpTemperatureSensor(GardenaEntity, SensorEntity):
    def __init__(
        self,
        coordinator: GardenaSmartLocalCoordinator,
        device: Pump,
    ) -> None:
        super().__init__(coordinator, device)
        self._attr_unique_id = f"{device.id}_outlet_temperature"
        self._attr_translation_key = "outlet_temperature"
        self._attr_device_class = SensorDeviceClass.TEMPERATURE
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS

    @property
    def native_value(self) -> float | None:
        device = self.coordinator.data.get(self._device.id)
        if not device:
            return None
        temp = device.outlet_temperature
        return float(temp) if temp is not None else None


class GardenaPumpFlowRateSensor(GardenaEntity, SensorEntity):
    def __init__(
        self,
        coordinator: GardenaSmartLocalCoordinator,
        device: Pump,
    ) -> None:
        super().__init__(coordinator, device)
        self._attr_unique_id = f"{device.id}_flow_rate"
        self._attr_translation_key = "flow_rate"
        self._attr_device_class = SensorDeviceClass.VOLUME_FLOW_RATE
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_native_unit_of_measurement = UnitOfVolumeFlowRate.LITERS_PER_HOUR

    @property
    def native_value(self) -> float | None:
        device = self.coordinator.data.get(self._device.id)
        if not device:
            return None
        rate = device.flow_rate
        return float(rate) if rate is not None else None


class GardenaPumpFlowTotalSensor(GardenaEntity, SensorEntity):
    def __init__(
        self,
        coordinator: GardenaSmartLocalCoordinator,
        device: Pump,
    ) -> None:
        super().__init__(coordinator, device)
        self._attr_unique_id = f"{device.id}_flow_total"
        self._attr_translation_key = "total_flow"
        self._attr_device_class = SensorDeviceClass.WATER
        self._attr_state_class = SensorStateClass.TOTAL_INCREASING
        self._attr_native_unit_of_measurement = UnitOfVolume.CUBIC_METERS

    @property
    def native_value(self) -> float | None:
        device = self.coordinator.data.get(self._device.id)
        if not device:
            return None
        total = device.flow_total
        return float(total) if total is not None else None


class GardenaPumpFlowSinceResetSensor(GardenaEntity, SensorEntity):
    def __init__(
        self,
        coordinator: GardenaSmartLocalCoordinator,
        device: Pump,
    ) -> None:
        super().__init__(coordinator, device)
        self._attr_unique_id = f"{device.id}_flow_since_reset"
        self._attr_translation_key = "flow_since_reset"
        self._attr_device_class = SensorDeviceClass.WATER
        self._attr_state_class = SensorStateClass.TOTAL_INCREASING
        self._attr_native_unit_of_measurement = UnitOfVolume.CUBIC_METERS

    @property
    def native_value(self) -> float | None:
        device = self.coordinator.data.get(self._device.id)
        if not device:
            return None
        flow = device.flow_since_last_reset
        return float(flow) if flow is not None else None


class GardenaPumpStateSensor(GardenaEntity, SensorEntity):
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options: ClassVar = [str(state) for state in PumpState]

    def __init__(
        self,
        coordinator: GardenaSmartLocalCoordinator,
        device: Pump,
    ) -> None:
        super().__init__(coordinator, device)
        self._attr_unique_id = f"{device.id}_pump_state"
        self._attr_translation_key = "pump_state"
        self._attr_entity_category = EntityCategory.DIAGNOSTIC

    @property
    def native_value(self) -> str | None:
        device = self.coordinator.data.get(self._device.id)
        if not device:
            return None
        state = device.pump_state
        return str(state) if state is not None else None


class GardenaScheduleCountSensor(GardenaEntity, SensorEntity):
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_entity_registry_enabled_default = False
    _attr_translation_key = "schedule_count"
    _attr_icon = "mdi:calendar-check"

    def __init__(
        self,
        coordinator: GardenaSmartLocalCoordinator,
        device: Device,
    ) -> None:
        super().__init__(coordinator, device)
        self._attr_unique_id = f"{device.id}_schedule_count"
        self._attr_state_class = SensorStateClass.MEASUREMENT

    @property
    def native_value(self) -> int | None:
        device = self.coordinator.data.get(self._device.id)
        if not device:
            return None
        return device.schedule_count


class GardenaFirmwareUpdateStateSensor(GardenaEntity, SensorEntity):
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options: ClassVar = [str(state) for state in FirmwareUpdateState]

    def __init__(
        self,
        coordinator: GardenaSmartLocalCoordinator,
        device: Device,
    ) -> None:
        super().__init__(coordinator, device)
        self._attr_unique_id = f"{device.id}_firmware_update_state"
        self._attr_translation_key = "firmware_update_state"
        self._attr_entity_category = EntityCategory.DIAGNOSTIC

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        await self.coordinator.async_refresh_firmware(self._device.id)

    @property
    def native_value(self) -> str | None:
        device = self.coordinator.data.get(self._device.id)
        if not device:
            return None
        state = device.firmware_update_state
        return str(state) if state is not None else None


class GardenaMowerLastErrorSensor(GardenaEntity, SensorEntity):
    """Last error code the mower reported; it stays after the error clears."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_translation_key = "last_error"
    _attr_icon = "mdi:alert-circle-outline"

    def __init__(
        self,
        coordinator: GardenaSmartLocalCoordinator,
        device: Device,
    ) -> None:
        super().__init__(coordinator, device)
        self._attr_unique_id = f"{device.id}_last_error"

    @property
    def native_value(self) -> str | None:
        device = self.coordinator.data.get(self._device.id)
        if not device:
            return None
        return mower_helpers.error_code_to_state(
            mower_helpers.get_last_error_code(device)
        )

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        device = self.coordinator.data.get(self._device.id)
        code: int | None = None
        timestamp: datetime | None = None
        if device:
            code = mower_helpers.get_last_error_code(device)
            timestamp = mower_helpers.get_last_error_timestamp(device)
        # raw_code is what the calibration automation pairs with the cloud text
        return {"raw_code": code, "timestamp": timestamp}


@dataclass(frozen=True, kw_only=True)
class GardenaMowerStatisticDescription(SensorEntityDescription):
    """A lifetime counter read from a ``lemonbeat`` resource of the mower."""

    resource_name: str


MOWER_STATISTICS: tuple[GardenaMowerStatisticDescription, ...] = (
    GardenaMowerStatisticDescription(
        key="cutting_time",
        translation_key="cutting_time",
        resource_name="cutting_time",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.HOURS,
        icon="mdi:fence",
    ),
    GardenaMowerStatisticDescription(
        key="running_time",
        translation_key="running_time",
        resource_name="running_time",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.HOURS,
        icon="mdi:timer-cog-outline",
    ),
    GardenaMowerStatisticDescription(
        key="charging_cycles",
        translation_key="charging_cycles",
        resource_name="charging_cycles",
        icon="mdi:battery-sync",
    ),
    GardenaMowerStatisticDescription(
        key="collisions",
        translation_key="collisions",
        resource_name="collisions",
        icon="mdi:car-brake-alert",
    ),
)


class GardenaMowerStatisticSensor(GardenaEntity, SensorEntity):
    entity_description: GardenaMowerStatisticDescription
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_state_class = SensorStateClass.TOTAL_INCREASING

    def __init__(
        self,
        coordinator: GardenaSmartLocalCoordinator,
        device: Device,
        description: GardenaMowerStatisticDescription,
    ) -> None:
        super().__init__(coordinator, device)
        self.entity_description = description
        self._attr_unique_id = f"{device.id}_{description.key}"

    @property
    def native_value(self) -> int | None:
        device = self.coordinator.data.get(self._device.id)
        if not device:
            return None
        return mower_helpers.get_lemonbeat_int(
            device, self.entity_description.resource_name
        )
