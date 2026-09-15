# SPDX-FileCopyrightText: 2026 GARDENA GmbH
#
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import logging
from collections.abc import Callable

from gardena_smart_local_api.devices.device import Device
from gardena_smart_local_api.messages import EgressMessageList, Reply
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    CONF_MOWER_DURATION,
    CONF_POWER_DURATION,
    CONF_PUMP_DURATION,
    CONF_VALVE_DURATIONS,
    DEFAULT_MOWER_DURATION_HOURS,
    DEFAULT_POWER_DURATION_MINUTES,
    DEFAULT_PUMP_DURATION_MINUTES,
    DEFAULT_VALVE_DURATION_MINUTES,
    DOMAIN,
)
from .coordinator import COMMAND_REPLY_TIMEOUT, GardenaSmartLocalCoordinator

_LOGGER = logging.getLogger(__name__)

# Builds the entities one device provides on a platform, keyed by a name that is
# unique per device on that platform (e.g. "temperature" or "valve_0"). The
# values create the entity, so only entities that are actually new get built.
type EntityFactories = dict[str, Callable[[], Entity]]


def find_device_subentry_id(entry: ConfigEntry, device_id: str) -> str | None:
    return next(
        (
            subentry_id
            for subentry_id, se in entry.subentries.items()
            if se.data.get("device_id") == device_id
        ),
        None,
    )


@callback
def async_setup_device_entities(
    entry: ConfigEntry,
    coordinator: GardenaSmartLocalCoordinator,
    async_add_entities: AddConfigEntryEntitiesCallback,
    entities_for_device: Callable[[Device], EntityFactories],
) -> None:
    known: set[tuple[str, str]] = set()

    @callback
    def _add_new_entities() -> None:
        current: dict[tuple[str, str], Callable[[], Entity]] = {}
        for device in (coordinator.data or {}).values():
            for name, factory in entities_for_device(device).items():
                current[(device.id, name)] = factory

        # Forget entities whose device (or valve) is gone, also when no device
        # is left at all, so a device that is included again gets its entities
        # back.
        known.intersection_update(current)

        entities_by_subentry_id: dict[str | None, list[Entity]] = {}
        for (device_id, name), factory in current.items():
            if (device_id, name) in known:
                continue
            known.add((device_id, name))
            sid = find_device_subentry_id(entry, device_id)
            entities_by_subentry_id.setdefault(sid, []).append(factory())
            _LOGGER.info("Adding %s entity for device %s", name, device_id)
        for sid, entities in entities_by_subentry_id.items():
            async_add_entities(entities, config_subentry_id=sid)

    entry.async_on_unload(coordinator.async_add_listener(_add_new_entities))
    _add_new_entities()


def get_valve_duration_minutes(
    entry: ConfigEntry, device_id: str, valve_id: int
) -> int:
    # Falls back to the default for devices without a subentry, and for valves
    # the user has never configured. Keys are strings because subentry data
    # round-trips through JSON.
    subentry_id = find_device_subentry_id(entry, device_id)
    if subentry_id is None:
        return DEFAULT_VALVE_DURATION_MINUTES
    durations = entry.subentries[subentry_id].data.get(CONF_VALVE_DURATIONS, {})
    minutes = durations.get(str(valve_id))
    if not isinstance(minutes, int):
        return DEFAULT_VALVE_DURATION_MINUTES
    return minutes


@callback
def async_set_valve_duration_minutes(
    hass: HomeAssistant,
    entry: ConfigEntry,
    device_id: str,
    valve_id: int,
    minutes: int,
) -> None:
    subentry_id = find_device_subentry_id(entry, device_id)
    if subentry_id is None:
        return
    subentry = entry.subentries[subentry_id]
    durations = dict(subentry.data.get(CONF_VALVE_DURATIONS, {}))
    durations[str(valve_id)] = minutes
    hass.config_entries.async_update_subentry(
        entry, subentry, data={**subentry.data, CONF_VALVE_DURATIONS: durations}
    )


def get_power_duration_minutes(entry: ConfigEntry, device_id: str) -> int:
    # Falls back to the default for devices without a subentry, and for
    # outlets the user has never configured.
    subentry_id = find_device_subentry_id(entry, device_id)
    if subentry_id is None:
        return DEFAULT_POWER_DURATION_MINUTES
    minutes = entry.subentries[subentry_id].data.get(CONF_POWER_DURATION)
    if not isinstance(minutes, int):
        return DEFAULT_POWER_DURATION_MINUTES
    return minutes


@callback
def async_set_power_duration_minutes(
    hass: HomeAssistant,
    entry: ConfigEntry,
    device_id: str,
    minutes: int,
) -> None:
    subentry_id = find_device_subentry_id(entry, device_id)
    if subentry_id is None:
        return
    subentry = entry.subentries[subentry_id]
    hass.config_entries.async_update_subentry(
        entry, subentry, data={**subentry.data, CONF_POWER_DURATION: minutes}
    )


def get_pump_duration_minutes(entry: ConfigEntry, device_id: str) -> int:
    # Falls back to the default for devices without a subentry, and for pumps
    # the user has never configured.
    subentry_id = find_device_subentry_id(entry, device_id)
    if subentry_id is None:
        return DEFAULT_PUMP_DURATION_MINUTES
    minutes = entry.subentries[subentry_id].data.get(CONF_PUMP_DURATION)
    if not isinstance(minutes, int):
        return DEFAULT_PUMP_DURATION_MINUTES
    return minutes


@callback
def async_set_pump_duration_minutes(
    hass: HomeAssistant,
    entry: ConfigEntry,
    device_id: str,
    minutes: int,
) -> None:
    subentry_id = find_device_subentry_id(entry, device_id)
    if subentry_id is None:
        return
    subentry = entry.subentries[subentry_id]
    hass.config_entries.async_update_subentry(
        entry, subentry, data={**subentry.data, CONF_PUMP_DURATION: minutes}
    )


def get_mower_duration_hours(entry: ConfigEntry, device_id: str) -> int:
    # Falls back to the default for devices without a subentry, and for mowers
    # the user has never configured.
    subentry_id = find_device_subentry_id(entry, device_id)
    if subentry_id is None:
        return DEFAULT_MOWER_DURATION_HOURS
    hours = entry.subentries[subentry_id].data.get(CONF_MOWER_DURATION)
    if not isinstance(hours, int):
        return DEFAULT_MOWER_DURATION_HOURS
    return hours


@callback
def async_set_mower_duration_hours(
    hass: HomeAssistant,
    entry: ConfigEntry,
    device_id: str,
    hours: int,
) -> None:
    subentry_id = find_device_subentry_id(entry, device_id)
    if subentry_id is None:
        return
    subentry = entry.subentries[subentry_id]
    hass.config_entries.async_update_subentry(
        entry, subentry, data={**subentry.data, CONF_MOWER_DURATION: hours}
    )


class GardenaEntity(CoordinatorEntity[GardenaSmartLocalCoordinator]):
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: GardenaSmartLocalCoordinator,
        device: Device,
    ) -> None:
        super().__init__(coordinator)
        self._device = device
        self._attr_device_info = dr.DeviceInfo(
            identifiers={(DOMAIN, device.id)},
            name=f"GARDENA {device.model_definition.name} {device.serial_number}",
            manufacturer="GARDENA",
            model=device.model_definition.name,
            model_id=device.model_definition.model_number,
            sw_version=device.software_version,
            hw_version=device.hardware_version,
            serial_number=device.serial_number,
        )

    @property
    def available(self) -> bool:
        if not self.coordinator.connected:
            return False
        device = self.coordinator.data.get(self._device.id)
        return bool(device and device.is_online)

    @callback
    def _handle_coordinator_update(self) -> None:
        """Keep the device registry sw_version in sync.

        DeviceInfo is only applied when the entity is added, so after a
        firmware up-/downgrade the device page would keep showing the old
        version until Home Assistant restarts.
        """
        device = self.coordinator.data.get(self._device.id)
        device_entry = self.device_entry
        if (
            device
            and device.software_version
            and isinstance(device_entry, dr.DeviceEntry)
            and device_entry.sw_version != device.software_version
        ):
            dr.async_get(self.hass).async_update_device(
                device_entry.id, sw_version=device.software_version
            )
        super()._handle_coordinator_update()

    async def _send_confirmed_command(
        self, request: EgressMessageList, timeout_sec: float = COMMAND_REPLY_TIMEOUT
    ) -> None:
        """Send a command and wait for the gateway to confirm it landed.

        Raises HomeAssistantError on timeout or rejection instead of letting
        the entity's state flip based on unconfirmed intermediate frames.
        """
        try:
            replies = await self.coordinator.send_request(
                self._device.id, request, wait_for_response_sec=timeout_sec
            )
        except TimeoutError as err:
            raise HomeAssistantError(
                f"Timed out waiting for the GARDENA smart Gateway to confirm "
                f"the command for device {self._device.id}"
            ) from err

        for msg in replies:
            if isinstance(msg, Reply) and not msg.success:
                raise HomeAssistantError(
                    f"GARDENA smart Gateway rejected the command for device "
                    f"{self._device.id}"
                )
