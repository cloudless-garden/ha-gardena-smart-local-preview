from __future__ import annotations

import logging

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import DOMAIN
from .coordinator import GardenaSmartLocalCoordinator
from .entity import GardenaEntity, find_device_subentry_id
from gardena_smart_local_api.devices.device import Device

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator: GardenaSmartLocalCoordinator = hass.data[DOMAIN][entry.entry_id]
    known_devices: set[str] = set()

    def _add_new_devices() -> None:
        if not coordinator.data:
            return
        entities_by_subentry_id: dict[str | None, list] = {}
        for device in coordinator.data.values():
            if (
                hasattr(device, "build_set_button_config_time_obj")
                and device.id not in known_devices
            ):
                known_devices.add(device.id)
                sid = find_device_subentry_id(entry, device.id)
                entities_by_subentry_id.setdefault(sid, []).append(
                    GardenaButtonConfigTime(coordinator, device)
                )
                _LOGGER.info(
                    "Adding new button config time entity for device %s", device.id
                )
        for sid, entities in entities_by_subentry_id.items():
            async_add_entities(entities, config_subentry_id=sid)

    coordinator.async_add_listener(_add_new_devices)


class GardenaButtonConfigTime(GardenaEntity, NumberEntity):
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
        super().__init__(coordinator, device)
        self._attr_unique_id = f"{device.id}_button_config_time"
        self._attr_name = "Button Time"
        self._attr_icon = "mdi:timer-outline"

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
