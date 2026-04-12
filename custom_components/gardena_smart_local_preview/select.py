from __future__ import annotations

import logging

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import GardenaSmartLocalCoordinator
from .entity import GardenaEntity
from gardena_smart_local_api.devices import Pump
from gardena_smart_local_api.devices.irrigation import OperatingMode

_LOGGER = logging.getLogger(__name__)

_MODE_TO_OPTION: dict[OperatingMode, str] = {
    OperatingMode.SCHEDULED: "scheduled",
    OperatingMode.AUTOMATIC: "automatic",
}
_OPTION_TO_MODE: dict[str, OperatingMode] = {v: k for k, v in _MODE_TO_OPTION.items()}


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
            if isinstance(device, Pump) and device.id not in known_devices:
                known_devices.add(device.id)
                new_entities.append(GardenaPumpOperatingModeSelect(coordinator, device))
                _LOGGER.info("Adding operating mode select for device %s", device.id)
        if new_entities:
            async_add_entities(new_entities)

    coordinator.async_add_listener(_add_new_devices)


class GardenaPumpOperatingModeSelect(GardenaEntity, SelectEntity):
    _attr_options = list(_OPTION_TO_MODE.keys())

    def __init__(
        self,
        coordinator: GardenaSmartLocalCoordinator,
        device: Pump,
    ) -> None:
        super().__init__(coordinator, device)
        self._attr_unique_id = f"{device.id}_operating_mode"
        self._attr_name = "Operating Mode"

    @property
    def current_option(self) -> str | None:
        device = self.coordinator.data.get(self._device.id)
        if not device:
            return None
        mode = device.operating_mode
        return _MODE_TO_OPTION.get(mode) if mode is not None else None

    async def async_select_option(self, option: str) -> None:
        mode = _OPTION_TO_MODE[option]
        await self.coordinator.send_request(
            self._device.id,
            self._device.build_set_operating_mode_obj(mode),
        )
        _LOGGER.info("Set operating mode for device %s to %s", self._device.id, option)
