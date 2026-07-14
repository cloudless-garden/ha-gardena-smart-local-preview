# SPDX-FileCopyrightText: 2026 GARDENA GmbH
#
# SPDX-License-Identifier: Apache-2.0

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr

from .const import DOMAIN
from .coordinator import GardenaSmartLocalCoordinator

TO_REDACT = {CONF_PASSWORD}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    coordinator: GardenaSmartLocalCoordinator = entry.runtime_data
    devices = {}
    if coordinator.data:
        devices = coordinator.data.model_dump(mode="json", exclude_none=True)
    return {
        "entry_data": async_redact_data(dict(entry.data), TO_REDACT),
        "entry_options": async_redact_data(dict(entry.options), TO_REDACT),
        "devices": devices,
    }


async def async_get_device_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry, device: dr.DeviceEntry
) -> dict[str, Any]:
    coordinator: GardenaSmartLocalCoordinator = entry.runtime_data
    device_id = None
    # device.identifiers can hold entries from other integrations, so pick ours
    for domain, identifier in device.identifiers:
        if domain == DOMAIN:
            device_id = identifier
            break

    gardena_device = None
    if device_id:
        gardena_device = coordinator.data.get(device_id)

    device_data = None
    if gardena_device:
        device_data = gardena_device.model_dump(mode="json", exclude_none=True)

    return {"device": device_data}
