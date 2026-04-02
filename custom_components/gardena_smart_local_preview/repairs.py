from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.components.repairs import RepairsFlow
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult

from .const import DOMAIN


async def async_create_fix_flow(
    hass: HomeAssistant,
    issue_id: str,
    data: dict[str, Any] | None,
) -> RepairsFlow:
    assert data is not None
    return IncludeDeviceRepairFlow(
        entry_id=data["entry_id"],
        instance_id=data["instance_id"],
        identifier=data["identifier"],
    )


class IncludeDeviceRepairFlow(RepairsFlow):
    def __init__(self, entry_id: str, instance_id: str, identifier: str) -> None:
        self._entry_id = entry_id
        self._instance_id = instance_id
        self._identifier = identifier

    async def async_step_init(self, user_input: dict | None = None) -> FlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            coordinator = self.hass.data[DOMAIN].get(self._entry_id)
            if coordinator is None:
                return self.async_abort(reason="coordinator_not_found")

            success = await coordinator.async_include_device(self._instance_id)
            if success:
                return self.async_create_entry(title="", data={})
            errors["base"] = "inclusion_failed"

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema({}),
            errors=errors,
            description_placeholders={"identifier": self._identifier},
        )
