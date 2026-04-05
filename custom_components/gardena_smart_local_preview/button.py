from __future__ import annotations

import logging

from homeassistant.components.button import ButtonEntity
from homeassistant.const import EntityCategory
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import GardenaSmartLocalCoordinator

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
            if hasattr(device, "build_identify_obj") and device.id not in known_devices:
                known_devices.add(device.id)
                new_entities.append(GardenaIdentifyButton(coordinator, device))
                _LOGGER.info("Adding identify button for device %s", device.id)
        if new_entities:
            async_add_entities(new_entities)

    coordinator.async_add_listener(_add_new_devices)


class GardenaIdentifyButton(
    CoordinatorEntity[GardenaSmartLocalCoordinator], ButtonEntity
):
    _attr_has_entity_name = True

    def __init__(
        self, coordinator: GardenaSmartLocalCoordinator, device: object
    ) -> None:
        super().__init__(coordinator)
        self._device = device
        self._attr_unique_id = f"{device.id}_identify"
        self._attr_name = "Identify"
        self._attr_entity_category = EntityCategory.DIAGNOSTIC
        self._attr_device_info = dr.DeviceInfo(
            identifiers={(DOMAIN, device.id)},
            name=f"GARDENA {device.model_definition.name}",
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

    async def async_press(self) -> None:
        await self.coordinator.send_request(
            self._device.id,
            self._device.build_identify_obj(),
        )
        _LOGGER.info("Sent identify request for device %s", self._device.id)
