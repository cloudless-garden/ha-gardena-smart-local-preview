# SPDX-FileCopyrightText: 2026 GARDENA GmbH
#
# SPDX-License-Identifier: Apache-2.0

"""Position of GARDENA mowers that report it (LONA / Gen2)."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from functools import partial
from typing import Any

from gardena_smart_local_api.devices import MowerState
from gardena_smart_local_api.devices.device import Device
from homeassistant.components.device_tracker import SourceType
from homeassistant.components.device_tracker.config_entry import TrackerEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from .coordinator import GardenaSmartLocalCoordinator
from .entity import (
    EntityFactories,
    GardenaEntity,
    async_setup_device_entities,
    get_position_reporting_enabled,
)

_LOGGER = logging.getLogger(__name__)

# Position reporting sends one command per renewal, never concurrently
PARALLEL_UPDATES = 1

# The gateway stops position reporting after at most 3600 s, so it has to be
# renewed while the mower is out. Renewing a bit early keeps the map live.
POSITION_REPORTING_TIMEOUT = 3600
POSITION_REPORTING_RENEWAL = timedelta(minutes=50)
# Reporting costs radio and battery, so it only runs while the mower is out.
ACTIVE_STATES = frozenset({MowerState.LEAVING, MowerState.MOWING, MowerState.RETURNING})
# The raw GNSS horizontal accuracy is assumed to be in millimetres (not
# documented by the schema); the raw value is exposed as an attribute too.
GNSS_ACCURACY_TO_METERS = 0.001


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator: GardenaSmartLocalCoordinator = entry.runtime_data

    def _entities_for_device(device: Device) -> EntityFactories:
        entities: EntityFactories = {}
        if hasattr(device, "build_start_position_reporting_obj"):
            entities["position"] = partial(
                GardenaMowerTracker, coordinator, entry, device
            )
        return entities

    async_setup_device_entities(
        entry, coordinator, async_add_entities, _entities_for_device
    )


class GardenaMowerTracker(GardenaEntity, TrackerEntity):
    _attr_translation_key = "position"
    _attr_source_type = SourceType.GPS

    def __init__(
        self,
        coordinator: GardenaSmartLocalCoordinator,
        entry: ConfigEntry,
        device: Device,
    ) -> None:
        super().__init__(coordinator, device)
        self._entry = entry
        self._attr_unique_id = f"{device.id}_position"
        self._reporting_requested_at: datetime | None = None

    def _position(self) -> Any | None:
        device = self.coordinator.data.get(self._device.id)
        return device.position if device else None

    @property
    def latitude(self) -> float | None:
        position = self._position()
        return position.latitude if position else None

    @property
    def longitude(self) -> float | None:
        position = self._position()
        return position.longitude if position else None

    @property
    def location_accuracy(self) -> float:
        position = self._position()
        if position is None:
            return 0
        raw = getattr(position, "gnss_horizontal_accuracy", None)
        if raw is None:
            raw = getattr(position, "accuracy", None)
        return raw * GNSS_ACCURACY_TO_METERS if raw is not None else 0

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        position = self._position()
        if position is None:
            return {}
        return position.model_dump(exclude={"latitude", "longitude"})

    def position_reporting_due(self, now: datetime) -> bool:
        if not get_position_reporting_enabled(self._entry, self._device.id):
            return False
        device = self.coordinator.data.get(self._device.id)
        if not device or device.state not in ACTIVE_STATES:
            return False
        return (
            self._reporting_requested_at is None
            or now - self._reporting_requested_at >= POSITION_REPORTING_RENEWAL
        )

    async def async_send_position_reporting(self, seconds: int) -> bool:
        try:
            await self._send_confirmed_command(
                self._device.build_start_position_reporting_obj(seconds)
            )
        except HomeAssistantError as err:
            _LOGGER.warning(
                "Could not start position reporting for %s: %s", self._device.id, err
            )
            return False
        _LOGGER.debug("Position reporting for %s on for %ss", self._device.id, seconds)
        return True

    @callback
    def schedule_position_reporting(self) -> None:
        # Mark first so the burst of events while mowing schedules one request
        self._reporting_requested_at = dt_util.utcnow()

        async def _send() -> None:
            if not await self.async_send_position_reporting(POSITION_REPORTING_TIMEOUT):
                self._reporting_requested_at = None

        # Tied to the entry so an unload cancels a request still in flight
        self._entry.async_create_background_task(
            self.hass, _send(), f"gardena_position_reporting_{self._device.id}"
        )

    @callback
    def _handle_coordinator_update(self) -> None:
        if self.position_reporting_due(dt_util.utcnow()):
            self.schedule_position_reporting()
        super()._handle_coordinator_update()
