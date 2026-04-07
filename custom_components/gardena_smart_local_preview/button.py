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
