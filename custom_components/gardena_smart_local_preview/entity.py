# SPDX-FileCopyrightText: 2026 GARDENA GmbH
#
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from gardena_smart_local_api.devices.device import Device
from gardena_smart_local_api.messages import EgressMessageList, Reply
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    CONF_PUMP_DURATION,
    CONF_VALVE_DURATIONS,
    DEFAULT_PUMP_DURATION_MINUTES,
    DEFAULT_VALVE_DURATION_MINUTES,
    DOMAIN,
)
from .coordinator import COMMAND_REPLY_TIMEOUT, GardenaSmartLocalCoordinator


def find_device_subentry_id(entry: ConfigEntry, device_id: str) -> str | None:
    return next(
        (
            subentry_id
            for subentry_id, se in entry.subentries.items()
            if se.data.get("device_id") == device_id
        ),
        None,
    )


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
        if (
            device
            and device.software_version
            and self.device_entry
            and self.device_entry.sw_version != device.software_version
        ):
            dr.async_get(self.hass).async_update_device(
                self.device_entry.id, sw_version=device.software_version
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
