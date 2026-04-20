import asyncio
import base64
import logging
from dataclasses import dataclass

import aiohttp
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util.ssl import get_default_no_verify_context

from gardena_smart_local_api.devices import (
    Device,
    DeviceMap,
    build_discovery_obj,
    build_inclusion_obj,
    create_devices_from_messages,
)
from gardena_smart_local_api.messages import (
    Reply,
    Event,
    EgressMessageList,
    IngressMessageList,
)
from gardena_smart_local_api.sgtin96 import parse_sgtin96

INCLUDE_REPLY_TIMEOUT = 10
EXCLUDE_REPLY_TIMEOUT = 10
INCLUDABLE_DEVICE_HEARTBEAT_TIMEOUT = 25


@dataclass
class IncludableDeviceInfo:
    instance_id: str
    service: str
    device_name: str


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
        self._msg_queue: asyncio.Queue[str] = asyncio.Queue()
        self._pending_replies: dict[str, asyncio.Future[Reply]] = {}
        self._includable_devices: dict[str, IncludableDeviceInfo] = {}
        self._includable_timeouts: dict[str, asyncio.TimerHandle] = {}

    async def _async_update_data(self) -> DeviceMap:
        return self._devices

    async def async_connect(self) -> None:
        if self._ssl_context is None:
            self._ssl_context = get_default_no_verify_context()
        self._task = self.hass.async_create_background_task(
            self._ws_loop(), "gardena_smart_local_preview_websocket"
        )

    async def async_disconnect(self) -> None:
        for handle in self._includable_timeouts.values():
            handle.cancel()
        self._includable_timeouts.clear()
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _ws_loop(self) -> None:
        while True:
            reader_task = None
            consumer_task = None
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

                        reader_task = self.hass.async_create_background_task(
                            self._ws_reader(ws),
                            "gardena_smart_local_preview_ws_reader",
                        )
                        consumer_task = self.hass.async_create_background_task(
                            self._msg_consumer(),
                            "gardena_smart_local_preview_msg_consumer",
                        )

                        await self._do_discovery()

                        # Block until the reader exits (disconnect / error)
                        await reader_task

            except asyncio.CancelledError:
                _LOGGER.debug("WebSocket loop cancelled")
                break
            except Exception as err:
                _LOGGER.error("WebSocket error: %s", err)
                await asyncio.sleep(5)
            finally:
                self._ws = None
                for task in (reader_task, consumer_task):
                    if task and not task.done():
                        task.cancel()
                        try:
                            await task
                        except (asyncio.CancelledError, Exception):
                            pass
                # Cancel any pending reply futures so waiters don't hang
                for fut in self._pending_replies.values():
                    if not fut.done():
                        fut.cancel()
                self._pending_replies.clear()

    async def _ws_reader(self, ws: aiohttp.ClientWebSocketResponse) -> None:
        async for msg in ws:
            match msg.type:
                case aiohttp.WSMsgType.TEXT:
                    await self._msg_queue.put(msg.data)
                case aiohttp.WSMsgType.BINARY:
                    await self._msg_queue.put(msg.data.decode("utf-8"))
                case aiohttp.WSMsgType.ERROR:
                    _LOGGER.error("WebSocket error: %s", ws.exception())
                    break
                case aiohttp.WSMsgType.CLOSED | aiohttp.WSMsgType.CLOSING:
                    break

    async def _msg_consumer(self) -> None:
        while True:
            raw = await self._msg_queue.get()
            try:
                messages = IngressMessageList.model_validate_json(raw)
            except Exception:
                _LOGGER.debug("Ignoring non-list message from gateway: %s", raw)
                continue

            passthrough: IngressMessageList = IngressMessageList([])
            for msg in messages:
                if isinstance(msg, Reply) and msg.request_id in self._pending_replies:
                    fut = self._pending_replies.pop(msg.request_id)
                    if not fut.done():
                        fut.set_result(msg)
                else:
                    passthrough.append(msg)

            if passthrough:
                await self._handle_messages(passthrough)

    async def _do_discovery(self, broadcast: bool = True) -> None:
        discovery = build_discovery_obj()
        n = len(list(discovery))
        _LOGGER.debug("Sent discovery request, awaiting %d replies", n)

        try:
            replies = await self.send_request(
                "discovery", discovery, wait_for_response_sec=30
            )
        except asyncio.TimeoutError:
            raise RuntimeError(
                f"Timed out waiting for discovery replies (expected {n})"
            )

        devices = await create_devices_from_messages(replies)
        self._update_devices(devices)
        if broadcast:
            self.async_set_updated_data(self._devices)
        _LOGGER.info("Discovery complete, found %d device(s)", len(self._devices))

    async def _handle_messages(self, messages: IngressMessageList) -> None:
        try:
            _LOGGER.debug("Handling %d message(s)", len(messages))

            updated = False

            for msg in messages:
                if isinstance(msg, Event):
                    if msg.entity.path.object_name == "includable_device":
                        await self._handle_includable_event(msg)
                    elif msg.entity.device:
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
            _LOGGER.warning("Error handling messages (may be non-critical): %s", err)

    def _expire_includable(self, instance_id: str) -> None:
        _LOGGER.debug("Includable device %s heartbeat timed out, removing", instance_id)
        self._includable_devices.pop(instance_id, None)
        self._includable_timeouts.pop(instance_id, None)

    async def _handle_includable_event(self, event: Event) -> None:
        instance_id = event.entity.path.object_instance_id
        if instance_id is None:
            return

        if event.op == "delete":
            handle = self._includable_timeouts.pop(instance_id, None)
            if handle is not None:
                handle.cancel()
            self._includable_devices.pop(instance_id, None)
            _LOGGER.debug("Includable device %s removed (delete event)", instance_id)
            return

        # Reschedule heartbeat timeout on every update
        handle = self._includable_timeouts.pop(instance_id, None)
        if handle is not None:
            handle.cancel()
        self._includable_timeouts[instance_id] = self.hass.loop.call_later(
            INCLUDABLE_DEVICE_HEARTBEAT_TIMEOUT, self._expire_includable, instance_id
        )

        if instance_id in self._includable_devices:
            _LOGGER.debug(
                "Includable device %s heartbeat, rescheduled timeout", instance_id
            )
            return

        service = event.entity.service
        if service is None:
            return

        identifier = event.payload.get("identifier", {}).get("vs", instance_id)
        try:
            sgtin = parse_sgtin96(identifier)
            device_name = f"{await sgtin.get_model_name()} {sgtin.serial:08d}"
        except ValueError:
            device_name = identifier

        self._includable_devices[instance_id] = IncludableDeviceInfo(
            instance_id=instance_id,
            service=service,
            device_name=device_name,
        )
        _LOGGER.info("Discovered includable device: %s (%s)", instance_id, device_name)

    @property
    def includable_devices(self) -> dict[str, IncludableDeviceInfo]:
        return dict(self._includable_devices)

    async def async_include_device(self, instance_id: str) -> str | None:
        info = self._includable_devices.get(instance_id)
        if info is None:
            _LOGGER.error("No includable device with instance_id %s", instance_id)
            return None

        request = build_inclusion_obj(info.service, instance_id)
        try:
            replies = await self.send_request(
                instance_id, request, wait_for_response_sec=INCLUDE_REPLY_TIMEOUT
            )
        except asyncio.TimeoutError:
            _LOGGER.error("Timeout waiting for inclusion reply for %s", instance_id)
            return None
        except Exception as err:
            _LOGGER.error("Error including device %s: %s", instance_id, err)
            return None

        for msg in replies:
            if isinstance(msg, Reply) and msg.success:
                _LOGGER.info("Device %s included successfully", instance_id)
                known_ids = set(self._devices.keys())
                try:
                    # broadcast=False: the subentry doesn't exist yet at this
                    # point; the caller schedules async_set_updated_data as a
                    # task so it runs after _async_finish_flow adds the subentry.
                    await self._do_discovery(broadcast=False)
                except Exception as err:
                    _LOGGER.warning("Re-discovery after inclusion failed: %s", err)
                    return None
                new_ids = set(self._devices.keys()) - known_ids
                if not new_ids:
                    _LOGGER.warning(
                        "Included device %s not found in discovery", instance_id
                    )
                    return None
                device_id = next(iter(new_ids))
                _LOGGER.info("Included device_id: %s", device_id)
                return device_id

        _LOGGER.error("Inclusion of device %s failed", instance_id)
        return None

    async def async_exclude_device(self, device_id: str) -> bool:
        device = self._devices.get(device_id)
        if device is None:
            _LOGGER.error("No device with id %s", device_id)
            return False

        request = device.build_exclusion_device_obj()
        try:
            replies = await self.send_request(
                device_id, request, wait_for_response_sec=EXCLUDE_REPLY_TIMEOUT
            )
        except asyncio.TimeoutError:
            _LOGGER.error("Timeout waiting for exclusion reply for %s", device_id)
            return False
        except Exception as err:
            _LOGGER.error("Error excluding device %s: %s", device_id, err)
            return False

        for msg in replies:
            if isinstance(msg, Reply) and msg.success:
                _LOGGER.info("Device %s excluded successfully", device_id)
                return True

        _LOGGER.error("Exclusion of device %s failed", device_id)
        return False

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

    async def send_request(
        self,
        device_id: str,
        request: EgressMessageList,
        wait_for_response_sec: float = 0,
    ) -> IngressMessageList:
        if not self._ws:
            _LOGGER.error("WebSocket not connected")
            return IngressMessageList([])

        if wait_for_response_sec > 0:
            loop = asyncio.get_running_loop()
            pending_ids = {
                req.request_id for req in request.root if req.request_id is not None
            }
            futures: dict[str, asyncio.Future[Reply]] = {
                rid: loop.create_future() for rid in pending_ids
            }
            self._pending_replies.update(futures)

            await self._ws.send_str(request.model_dump_json())
            _LOGGER.debug("Sent request to device %s: %s", device_id, request)

            try:
                async with asyncio.timeout(wait_for_response_sec):
                    replies = await asyncio.gather(*futures.values())
            except asyncio.TimeoutError:
                for rid in pending_ids:
                    self._pending_replies.pop(rid, None)
                raise

            return IngressMessageList(list(replies))

        await self._ws.send_str(request.model_dump_json())
        _LOGGER.debug("Sent request to device %s: %s", device_id, request)
        return IngressMessageList([])
