import asyncio
import base64
import logging
import aiohttp
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util.ssl import get_default_no_verify_context

from gardena_smart_local_api.devices import (
    Device,
    DeviceMap,
    build_discovery_obj,
    create_devices_from_messages,
)
from gardena_smart_local_api.messages import (
    Reply,
    Event,
    EgressMessageList,
    IngressMessageList,
)

_LOGGER = logging.getLogger(__name__)


class GardenaSmartLocalCoordinator(DataUpdateCoordinator[DeviceMap]):
    def __init__(
        self,
        hass: HomeAssistant,
        host: str,
        port: int,
        password: str,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name="GARDENA smart local",
        )
        self.host = host
        self.port = port
        self.password = password
        self.uri = f"wss://{host}:{port}"

        auth_string = f"_:{password}"
        auth_bytes = auth_string.encode("utf-8")
        self.auth_b64 = base64.b64encode(auth_bytes).decode("ascii")

        self._ws = None
        self._task = None
        self._devices: DeviceMap = DeviceMap({})
        self._ssl_context = None

    async def _async_update_data(self) -> DeviceMap:
        return self._devices

    async def async_connect(self) -> None:
        if self._ssl_context is None:
            self._ssl_context = get_default_no_verify_context()
        self._task = self.hass.async_create_background_task(
            self._ws_loop(), "gardena_smart_local_preview_websocket"
        )

    async def async_disconnect(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _ws_loop(self) -> None:
        while True:
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.ws_connect(
                        self.uri,
                        ssl=self._ssl_context,
                        headers={"Authorization": f"Basic {self.auth_b64}"},
                    ) as ws:
                        self._ws = ws
                        _LOGGER.info(
                            "Connected to GARDENA local gateway at %s", self.uri
                        )

                        # Request device list immediately on connection
                        await self._request_devices()

                        # Listen for messages
                        async for msg in ws:
                            if msg.type == aiohttp.WSMsgType.TEXT:
                                await self._handle_message(msg.data)
                            elif msg.type == aiohttp.WSMsgType.BINARY:
                                await self._handle_message(msg.data.decode("utf-8"))
                            elif msg.type == aiohttp.WSMsgType.ERROR:
                                _LOGGER.error("WebSocket error: %s", ws.exception())
                                break
                            elif msg.type in (
                                aiohttp.WSMsgType.CLOSED,
                                aiohttp.WSMsgType.CLOSING,
                            ):
                                break

            except asyncio.CancelledError:
                _LOGGER.debug("WebSocket loop cancelled")
                break
            except Exception as err:
                # Log the error but keep retrying indefinitely with a delay
                _LOGGER.error("WebSocket error: %s", err)
                await asyncio.sleep(5)

    async def _request_devices(self) -> None:
        if not self._ws:
            return

        request = build_discovery_obj()
        await self._ws.send_str(str(request))
        _LOGGER.debug("Requested device list: %s", request)

    async def _handle_message(self, ws_message: str) -> None:
        try:
            _LOGGER.debug("Received WebSocket message: %s", ws_message)

            try:
                messages = IngressMessageList.model_validate_json(ws_message)
            except Exception:
                _LOGGER.debug("Ignoring non-list message from gateway: %s", ws_message)
                return

            updated = False

            if any(isinstance(msg, Reply) for msg in messages):
                devices = await create_devices_from_messages(messages)
                self._update_devices(devices)
                updated = True

            for msg in messages:
                if isinstance(msg, Event):
                    if msg.entity.device:
                        device_id = msg.entity.device
                        if device_id in self._devices:
                            _LOGGER.debug(
                                "Updating device %s with event: %s",
                                device_id,
                                msg,
                            )
                            self._devices[device_id].update_data(msg)
                            updated = True
                    else:
                        _LOGGER.debug(
                            "Event does not have device ID, ignoring: %s", msg
                        )

            if updated:
                self.async_set_updated_data(self._devices)

        except Exception as err:
            _LOGGER.warning(
                "Error handling message (may be non-critical): %s - Message: %s",
                err,
                ws_message,
            )

    def _update_device(self, device: Device) -> None:
        is_new = device.id not in self._devices
        self._devices[device.id] = device
        if is_new:
            _LOGGER.info(
                "Added new device: %s (%s)", device.id, device.model_definition.name
            )
        else:
            _LOGGER.debug(
                "Updated existing device: %s (%s)",
                device.id,
                device.model_definition.name,
            )

    def _update_devices(self, devices: DeviceMap) -> None:
        try:
            for device in devices.values():
                self._update_device(device)
        except Exception as err:
            _LOGGER.warning("Failed to update devices: %s", err)

    async def send_request(self, device_id: str, request: EgressMessageList) -> None:
        if not self._ws:
            _LOGGER.error("WebSocket not connected")
            return

        await self._ws.send_str(request.model_dump_json())
        _LOGGER.debug("Sent request to device %s: %s", device_id, request)
