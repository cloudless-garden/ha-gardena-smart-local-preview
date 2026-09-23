# SPDX-FileCopyrightText: 2026 GARDENA GmbH
#
# SPDX-License-Identifier: Apache-2.0

"""End-to-end setup of a config entry with a real Gen1 LONA mower."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from gardena_smart_local_api.devices import DeviceMap
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_PORT
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.gardena_smart_local_preview.const import DOMAIN
from custom_components.gardena_smart_local_preview.coordinator import (
    GardenaSmartLocalCoordinator,
)
from tests.common import POSITION_B64, make_gen1_mower

LEMONBEAT = {
    "status": {"vi": 1},  # OK_CUTTING_AUTO
    "position": {"vo": POSITION_B64},
    "last_error_code": {"vi": 15},
    "timestamp_last_error_code": {"vo": "arPA3g=="},
    "cutting_time": {"vi": 1269},
    "running_time": {"vi": 1345},
    "charging_cycles": {"vi": 933},
    "collisions": {"vi": 3120},
    "battery_level": {"vi": 99},
}


@pytest.fixture
async def setup_entry(hass: HomeAssistant) -> MockConfigEntry:
    device = make_gen1_mower(LEMONBEAT)

    async def fake_connect(self: GardenaSmartLocalCoordinator) -> None:
        self._ws = AsyncMock(closed=False)
        self._devices = DeviceMap({device.id: device})
        self.async_set_updated_data(self._devices)

    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_HOST: "gateway.local", CONF_PORT: 8443, CONF_PASSWORD: "x"},
    )
    entry.add_to_hass(hass)
    with (
        patch.object(GardenaSmartLocalCoordinator, "async_connect", fake_connect),
        patch.object(GardenaSmartLocalCoordinator, "async_disconnect", AsyncMock()),
        patch.object(
            GardenaSmartLocalCoordinator, "async_refresh_firmware", AsyncMock()
        ),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        yield entry


def _state(hass: HomeAssistant, platform: str, unique_id: str):
    entity_id = er.async_get(hass).async_get_entity_id(platform, DOMAIN, unique_id)
    assert entity_id, f"{platform} {unique_id} not registered"
    state = hass.states.get(entity_id)
    assert state is not None
    return state


async def test_tracker_publishes_gps_position(
    hass: HomeAssistant, setup_entry: MockConfigEntry
) -> None:
    state = _state(hass, "device_tracker", "dev-1_position")

    assert state.attributes["source_type"] == "gps"
    assert state.attributes["latitude"] == pytest.approx(47.3637)
    assert state.attributes["longitude"] == pytest.approx(8.5127)
    assert state.attributes["gps_accuracy"] == pytest.approx(2.5)
    assert state.attributes["lona_is_ready"] is True
    assert state.attributes["heading"] == pytest.approx(224.8)


async def test_mower_health_and_statistics_are_published(
    hass: HomeAssistant, setup_entry: MockConfigEntry
) -> None:
    assert _state(hass, "binary_sensor", "dev-1_problem").state == "off"
    last_error = _state(hass, "sensor", "dev-1_last_error")
    assert last_error.state == "code_15"
    assert last_error.attributes["raw_code"] == 15
    assert _state(hass, "sensor", "dev-1_cutting_time").state == "1269"
    assert _state(hass, "sensor", "dev-1_collisions").state == "3120"
    assert _state(hass, "lawn_mower", "dev-1_lawn_mower").state == "mowing"
