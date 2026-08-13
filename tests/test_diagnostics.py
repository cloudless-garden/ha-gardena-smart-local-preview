# SPDX-FileCopyrightText: 2026 GARDENA GmbH
#
# SPDX-License-Identifier: Apache-2.0

"""Tests for the GARDENA smart local diagnostics."""

from __future__ import annotations

from unittest.mock import MagicMock

from homeassistant.components.diagnostics import REDACTED
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_PORT
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.gardena_smart_local_preview import diagnostics
from custom_components.gardena_smart_local_preview.const import DOMAIN


def _entry(devices: dict | None) -> MockConfigEntry:
    config_entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_HOST: "192.168.1.50", CONF_PORT: 8080, CONF_PASSWORD: "secret"},
        options={"some_option": "value"},
    )
    runtime_data = MagicMock()
    runtime_data.data = MagicMock()
    runtime_data.data.__bool__.return_value = devices is not None
    runtime_data.data.model_dump.return_value = devices or {}

    device_mock = None
    if devices and "device-1" in devices:
        device_mock = MagicMock()
        device_mock.model_dump.return_value = devices["device-1"]
    runtime_data.data.get.return_value = device_mock

    config_entry.runtime_data = runtime_data
    return config_entry


async def test_config_entry_diagnostics_redacts_password(hass) -> None:
    entry = _entry({"device-1": {"id": "device-1"}})

    result = await diagnostics.async_get_config_entry_diagnostics(hass, entry)

    assert result["entry_data"][CONF_PASSWORD] == REDACTED
    assert result["entry_data"][CONF_HOST] == "192.168.1.50"
    assert result["entry_options"] == {"some_option": "value"}
    assert result["devices"] == {"device-1": {"id": "device-1"}}


async def test_config_entry_diagnostics_handles_no_devices(hass) -> None:
    entry = _entry(None)

    result = await diagnostics.async_get_config_entry_diagnostics(hass, entry)

    assert result["devices"] == {}


async def test_device_diagnostics_returns_matching_device(hass) -> None:
    entry = _entry({"device-1": {"id": "device-1", "name": "Water Control"}})
    device_entry = MagicMock(identifiers={(DOMAIN, "device-1")})

    result = await diagnostics.async_get_device_diagnostics(hass, entry, device_entry)

    assert result["device"] == {"id": "device-1", "name": "Water Control"}


async def test_device_diagnostics_returns_none_for_unmatched_device(hass) -> None:
    entry = _entry({"device-1": {"id": "device-1"}})
    device_entry = MagicMock(identifiers={("other_domain", "device-1")})

    result = await diagnostics.async_get_device_diagnostics(hass, entry, device_entry)

    assert result["device"] is None
