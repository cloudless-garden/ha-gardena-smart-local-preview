# SPDX-FileCopyrightText: 2026 GARDENA GmbH
#
# SPDX-License-Identifier: Apache-2.0

from unittest.mock import AsyncMock, MagicMock

import pytest

pytest_plugins = ["pytest_homeassistant_custom_component"]


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Enable loading of the custom integration in all tests."""
    return enable_custom_integrations


@pytest.fixture
def mock_device() -> MagicMock:
    """Return a device mock carrying the metadata every GARDENA entity reads."""
    device = MagicMock()
    device.id = "dev-1"
    device.serial_number = "00000001"
    device.software_version = "1.0.0"
    device.hardware_version = "1.0"
    device.model_definition.name = "Test Device"
    device.model_definition.model_number = "1"
    device.valve_ids = []
    return device


@pytest.fixture
def coordinator(mock_device: MagicMock) -> MagicMock:
    """Return a coordinator mock that knows the device and confirms commands."""
    coord = MagicMock()
    coord.connected = True
    coord.data = {mock_device.id: mock_device}
    coord.send_request = AsyncMock(return_value=[])
    return coord


@pytest.fixture
def entry() -> MagicMock:
    """Return a config entry mock without subentries."""
    cfg = MagicMock()
    cfg.subentries = {}
    return cfg


@pytest.fixture
def subentry(entry: MagicMock, mock_device: MagicMock) -> MagicMock:
    """Return a subentry for the device, registered on the config entry."""
    sub = MagicMock()
    sub.data = {"device_id": mock_device.id}
    entry.subentries["sub-1"] = sub
    return sub
