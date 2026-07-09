# SPDX-FileCopyrightText: 2026 GARDENA GmbH
#
# SPDX-License-Identifier: Apache-2.0

import asyncio
from unittest.mock import MagicMock

import aiohttp
import pytest
import pytest_asyncio
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.gardena_smart_local_preview.const import DOMAIN
from custom_components.gardena_smart_local_preview.coordinator import (
    GardenaSmartLocalCoordinator,
)

pytest_plugins = ["pytest_homeassistant_custom_component"]


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Enable loading of the custom integration in all tests."""
    return enable_custom_integrations


@pytest.fixture
def mock_device():
    """Factory for a MagicMock standing in for a gardena_smart_local_api Device."""

    def _make(
        device_id: str = "device-1",
        is_online: bool = True,
        name: str = "Water Control",
        model_number: str = "MOD-1",
        serial_number: str = "SN123",
    ) -> MagicMock:
        device = MagicMock()
        device.id = device_id
        device.is_online = is_online
        device.model_definition.name = name
        device.model_definition.model_number = model_number
        device.serial_number = serial_number
        device.software_version = "1.0"
        device.hardware_version = "2.0"
        return device

    return _make


@pytest.fixture
def spec_device():
    """Factory for a MagicMock(spec=...) standing in for a concrete Device subclass.

    Unlike `mock_device`, this restricts attribute access to what the real
    class actually defines, so `hasattr`/`isinstance` gates in platform
    `async_setup_entry` functions behave like they would against the real
    device.
    """

    def _make(
        spec_cls: type,
        device_id: str = "device-1",
        is_online: bool = True,
        name: str = "Test Device",
        model_number: str = "MOD-1",
        serial_number: str = "SN123",
        **attrs: object,
    ) -> MagicMock:
        # dir(spec_cls) misses pydantic model fields (id/data/model_definition),
        # which have no class-level attribute of their own; union them in so
        # the mock still restricts hasattr()/isinstance() like the real class.
        attr_names = set(dir(spec_cls)) | set(spec_cls.model_fields)
        device = MagicMock(spec=list(attr_names))
        device.__class__ = spec_cls
        device.id = device_id
        device.is_online = is_online
        device.model_definition.name = name
        device.model_definition.model_number = model_number
        device.serial_number = serial_number
        device.software_version = "1.0"
        device.hardware_version = "2.0"
        for key, value in attrs.items():
            setattr(device, key, value)
        return device

    return _make


@pytest_asyncio.fixture
async def coordinator(hass):
    """A real GardenaSmartLocalCoordinator bound to the test hass instance."""
    coord = GardenaSmartLocalCoordinator(hass, "192.168.1.50", 8080, "secret")
    yield coord
    await coord.async_disconnect()


@pytest.fixture
def entry(coordinator):
    """A MockConfigEntry wired up with the real `coordinator` fixture as runtime_data."""
    config_entry = MockConfigEntry(domain=DOMAIN, data={})
    config_entry.runtime_data = coordinator
    return config_entry


@pytest.fixture
def sync_devices(coordinator):
    """Publishes `coordinator._devices` as `coordinator.data` and fires listeners.

    Entity state properties read `coordinator.data`, which is distinct from
    `coordinator._devices` until this is called (mirrors real discovery).
    """

    def _sync() -> None:
        coordinator.async_set_updated_data(coordinator._devices)

    return _sync


@pytest.fixture
def setup_platform(hass):
    """Runs a platform module's async_setup_entry and returns the async_add_entities mock.

    Registers the coordinator listener; tests then populate
    `coordinator._devices` and call `coordinator.async_set_updated_data(...)`
    to trigger it, mirroring real dynamic device discovery.
    """

    async def _setup(module, config_entry) -> MagicMock:
        async_add_entities = MagicMock()
        await module.async_setup_entry(hass, config_entry, async_add_entities)
        return async_add_entities

    return _setup


class FakeWebSocket:
    """Minimal stand-in for aiohttp.ClientWebSocketResponse.

    After exhausting `messages`, iteration blocks (like an idle open
    connection) until `simulate_close()` is called, instead of ending the
    async-for immediately.
    """

    def __init__(self, messages: list[aiohttp.WSMessage] | None = None) -> None:
        self.messages = messages or []
        self.sent: list[str] = []
        self.closed = False
        self.close_code = 1000
        self._exception: Exception | None = None
        self._closed_event = asyncio.Event()

    def exception(self) -> Exception | None:
        return self._exception

    async def send_str(self, data: str) -> None:
        self.sent.append(data)

    def simulate_close(self, exception: Exception | None = None) -> None:
        self._exception = exception
        self.closed = True
        self._closed_event.set()

    def __aiter__(self):
        return self._aiter()

    async def _aiter(self):
        for msg in self.messages:
            yield msg
        await self._closed_event.wait()

    async def __aenter__(self) -> "FakeWebSocket":
        return self

    async def __aexit__(self, *exc_info: object) -> bool:
        return False


@pytest.fixture
def fake_ws():
    return FakeWebSocket
