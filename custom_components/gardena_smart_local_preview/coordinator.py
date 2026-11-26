# SPDX-FileCopyrightText: 2026 GARDENA GmbH
#
# SPDX-License-Identifier: Apache-2.0

import logging
from collections.abc import Iterable

from gardena_smart_local_api.client import (
    DeviceManager,
    IncludableDevice,
    InclusionError,
    RequestError,
)
from gardena_smart_local_api.devices import DeviceMap
from gardena_smart_local_api.messages import EgressMessageList, IngressMessageList
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

COMMAND_REPLY_TIMEOUT = 10

_LOGGER = logging.getLogger(__name__)


class GardenaSmartLocalCoordinator(DataUpdateCoordinator[DeviceMap]):
    config_entry: ConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: ConfigEntry,
        host: str,
        port: int,
        password: str,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=config_entry,
            name="GARDENA smart local",
        )
        self.host = host
        self.port = port
        # Keeps the connection open and the devices up to date, and reconnects
        # on its own. After a rejected password it stops instead of hammering
        # the gateway and starts the reauthentication flow, which reloads the
        # entry.
        self.manager = DeviceManager(
            host,
            port,
            password,
            session=async_get_clientsession(hass),
            on_devices_changed=self._on_devices_changed,
            on_disconnect=self._on_disconnect,
            on_auth_failed=self._on_auth_failed,
        )

    async def _async_update_data(self) -> DeviceMap:
        return self.manager.devices

    @property
    def uri(self) -> str:
        return self.manager.client.uri

    @property
    def connected(self) -> bool:
        """Return True if the WebSocket to the gateway is currently connected."""
        return self.manager.connected

    @property
    def includable_devices(self) -> dict[str, IncludableDevice]:
        return self.manager.includable_devices

    async def async_connect(self) -> None:
        await self.manager.connect()

    async def async_disconnect(self) -> None:
        await self.manager.disconnect()

    @callback
    def async_publish_devices(self) -> None:
        """Tell the entities that the devices changed."""
        self.async_set_updated_data(self.manager.devices)

    @callback
    def _on_devices_changed(self, device_ids: Iterable[str]) -> None:
        self.async_publish_devices()

    @callback
    def _on_disconnect(self) -> None:
        """Let entities re-check their availability once the connection drops."""
        self.async_update_listeners()

    @callback
    def _on_auth_failed(self) -> None:
        self.config_entry.async_start_reauth(self.hass)

    async def async_include_device(self, instance_id: str) -> str | None:
        """Include a device in inclusion mode and return its device id.

        The entities are not told about the new device. The caller does that
        with `async_publish_devices`, once the subentry of the device exists.
        """
        try:
            device = await self.manager.include_device(instance_id, notify=False)
        except InclusionError as err:
            _LOGGER.error("Inclusion of device %s failed: %s", instance_id, err)
            return None
        return device.id

    async def async_exclude_device(self, device_id: str) -> bool:
        try:
            await self.manager.exclude_device(device_id)
        except (RequestError, TimeoutError, ConnectionError) as err:
            _LOGGER.error("Exclusion of device %s failed: %s", device_id, err)
            return False
        return True

    async def async_refresh_firmware(self, device_id: str) -> None:
        try:
            await self.manager.refresh_firmware(device_id)
        except (RequestError, TimeoutError, ConnectionError) as err:
            _LOGGER.debug("Error refreshing firmware state for %s: %s", device_id, err)

    async def send_command(
        self,
        device_id: str,
        request: EgressMessageList,
        timeout: float = COMMAND_REPLY_TIMEOUT,
    ) -> IngressMessageList:
        """Send a request that changes a device and wait for the replies.

        Raises `RequestError` if the gateway rejects the request, `TimeoutError`
        if it does not answer in time, and `ConnectionError` if the connection
        is not open or drops.
        """
        return await self.manager.send_command(device_id, request, timeout)
