# SPDX-FileCopyrightText: 2026 GARDENA GmbH
#
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import logging

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import GardenaSmartLocalCoordinator
from .entity import GardenaEntity, find_device_subentry_id
from gardena_smart_local_api.devices import Pump
from gardena_smart_local_api.devices.irrigation import PumpOperatingMode

_LOGGER = logging.getLogger(__name__)

# Actions send commands to the gateway's local websocket — cap at 1 so HA
# serializes them instead of firing concurrent commands at the same connection
PARALLEL_UPDATES = 1

_MODE_TO_OPTION: dict[PumpOperatingMode, str] = {
    PumpOperatingMode.SCHEDULED: "scheduled",
    PumpOperatingMode.AUTOMATIC: "automatic",
}
_OPTION_TO_MODE: dict[str, PumpOperatingMode] = {
    v: k for k, v in _MODE_TO_OPTION.items()
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator: GardenaSmartLocalCoordinator = entry.runtime_data
    known_devices: set[str] = set()

    def _add_new_devices() -> None:
        if not coordinator.data:
            return
        known_devices.intersection_update(coordinator.data)
        entities_by_subentry_id: dict[str | None, list] = {}
        for device in coordinator.data.values():
            if isinstance(device, Pump) and device.id not in known_devices:
                known_devices.add(device.id)
                sid = find_device_subentry_id(entry, device.id)
                entities_by_subentry_id.setdefault(sid, []).append(
                    GardenaPumpOperatingModeSelect(coordinator, device)
                )
                _LOGGER.info("Adding operating mode select for device %s", device.id)
        for sid, entities in entities_by_subentry_id.items():
            async_add_entities(entities, config_subentry_id=sid)

    entry.async_on_unload(coordinator.async_add_listener(_add_new_devices))
    _add_new_devices()


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
