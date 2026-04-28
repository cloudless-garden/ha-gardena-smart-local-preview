from __future__ import annotations

import logging

from homeassistant.components.button import ButtonEntity
from homeassistant.const import EntityCategory
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import GardenaSmartLocalCoordinator
from .entity import GardenaEntity
from gardena_smart_local_api.devices.device import Device
from gardena_smart_local_api.devices import Pump

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: GardenaSmartLocalCoordinator = hass.data[DOMAIN][entry.entry_id]
    known_devices: set[str] = set()
    known_pump_devices: set[str] = set()

    def _add_new_devices() -> None:
        if not coordinator.data:
            return
        new_entities = []
        for device in coordinator.data.values():
            if hasattr(device, "build_identify_obj") and device.id not in known_devices:
                known_devices.add(device.id)
                new_entities.append(GardenaIdentifyButton(coordinator, device))
                _LOGGER.info("Adding identify button for device %s", device.id)
            if isinstance(device, Pump) and device.id not in known_pump_devices:
                known_pump_devices.add(device.id)
                new_entities.extend(
                    [
                        GardenaPumpResetFlowButton(coordinator, device),
                        GardenaPumpResetValveErrorsButton(coordinator, device),
                        GardenaPumpResetTemperatureMinMaxButton(coordinator, device),
                    ]
                )
                _LOGGER.info("Adding pump reset buttons for device %s", device.id)
        if new_entities:
            async_add_entities(new_entities)

    coordinator.async_add_listener(_add_new_devices)


class GardenaIdentifyButton(GardenaEntity, ButtonEntity):
    def __init__(
        self, coordinator: GardenaSmartLocalCoordinator, device: Device
    ) -> None:
        super().__init__(coordinator, device)
        self._attr_unique_id = f"{device.id}_identify"
        self._attr_name = "Identify"
        self._attr_icon = "mdi:crosshairs-gps"
        self._attr_entity_category = EntityCategory.DIAGNOSTIC

    async def async_press(self) -> None:
        await self.coordinator.send_request(
            self._device.id,
            self._device.build_identify_obj(),
        )
        _LOGGER.info("Sent identify request for device %s", self._device.id)


class GardenaPumpResetFlowButton(GardenaEntity, ButtonEntity):
    def __init__(self, coordinator: GardenaSmartLocalCoordinator, device: Pump) -> None:
        super().__init__(coordinator, device)
        self._attr_unique_id = f"{device.id}_reset_flow"
        self._attr_name = "Reset Resettable Flow"
        self._attr_entity_category = EntityCategory.CONFIG

    async def async_press(self) -> None:
        await self.coordinator.send_request(
            self._device.id,
            self._device.build_reset_flow_resettable_obj(),
        )
        _LOGGER.info("Reset resettable flow for device %s", self._device.id)


class GardenaPumpResetValveErrorsButton(GardenaEntity, ButtonEntity):
    def __init__(self, coordinator: GardenaSmartLocalCoordinator, device: Pump) -> None:
        super().__init__(coordinator, device)
        self._attr_unique_id = f"{device.id}_reset_valve_errors"
        self._attr_name = "Reset Valve Errors"
        self._attr_entity_category = EntityCategory.CONFIG

    async def async_press(self) -> None:
        await self.coordinator.send_request(
            self._device.id,
            self._device.build_reset_all_valve_errors_obj(),
        )
        _LOGGER.info("Reset valve errors for device %s", self._device.id)


class GardenaPumpResetTemperatureMinMaxButton(GardenaEntity, ButtonEntity):
    def __init__(self, coordinator: GardenaSmartLocalCoordinator, device: Pump) -> None:
        super().__init__(coordinator, device)
        self._attr_unique_id = f"{device.id}_reset_temperature_min_max"
        self._attr_name = "Reset Temperature Min/Max"
        self._attr_entity_category = EntityCategory.CONFIG

    async def async_press(self) -> None:
        await self.coordinator.send_request(
            self._device.id,
            self._device.build_reset_outlet_temperature_min_max_obj(),
        )
        _LOGGER.info("Reset temperature min/max for device %s", self._device.id)
