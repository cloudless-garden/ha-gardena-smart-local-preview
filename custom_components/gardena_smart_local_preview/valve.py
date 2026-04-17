from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.valve import ValveEntity, ValveEntityFeature
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import GardenaSmartLocalCoordinator
from .entity import GardenaEntity
from gardena_smart_local_api.devices import Device

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
            if device.id not in known_devices and hasattr(device, "valve_ids"):
                known_devices.add(device.id)
                for valve_id in device.valve_ids:
                    new_entities.append(GardenaValve(coordinator, device, valve_id))
                    _LOGGER.info(
                        "Adding new valve entity for device %s, valve %s",
                        device.id,
                        valve_id,
                    )
        if new_entities:
            async_add_entities(new_entities)

    coordinator.async_add_listener(_add_new_devices)


class GardenaValve(GardenaEntity, ValveEntity):
    def __init__(
        self,
        coordinator: GardenaSmartLocalCoordinator,
        device: Device,
        valve_id: int = 0,
    ) -> None:
        super().__init__(coordinator, device)
        self._valve_id = valve_id
        self._attr_unique_id = f"{device.id}_valve_{valve_id}"
        self._attr_name = f"Valve {valve_id + 1}" if len(device.valve_ids) > 1 else None
        self._attr_reports_position = False
        self._attr_supported_features = (
            ValveEntityFeature.OPEN | ValveEntityFeature.CLOSE
        )

    @property
    def is_closed(self) -> bool | None:
        device = self.coordinator.data.get(self._device.id)
        if not device:
            return None
        is_opened = device.is_valve_open(self._valve_id)
        _LOGGER.debug(
            "Valve %s valve_id=%s, is_opened=%s, returning is_closed=%s",
            self._device.id,
            self._valve_id,
            is_opened,
            not is_opened,
        )
        if is_opened is None:
            return None
        return not is_opened

    async def async_open_valve(self, **kwargs: Any) -> None:
        await self.coordinator.send_request(
            self._device.id,
            self._device.build_open_valve_obj(self._valve_id, 1800),
        )
        _LOGGER.info("Opening valve %s valve_id=%s", self._device.id, self._valve_id)

    async def async_close_valve(self, **kwargs: Any) -> None:
        await self.coordinator.send_request(
            self._device.id,
            self._device.build_close_valve_obj(self._valve_id),
        )
        _LOGGER.info("Closing valve %s valve_id=%s", self._device.id, self._valve_id)
