import asyncio
import base64
import logging
import aiohttp
from homeassistant.core import HomeAssistant
from homeassistant.helpers.issue_registry import (
    async_create_issue,
    async_delete_issue,
    IssueSeverity,
)
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

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

INCLUDE_REPLY_TIMEOUT = 10
INCLUDABLE_DEVICE_HEARTBEAT_TIMEOUT = 25


class GardenaSmartLocalCoordinator(DataUpdateCoordinator[DeviceMap]):
    def __init__(
        self,
        hass: HomeAssistant,
        entry_id: str,
        host: str,
        port: int,
        password: str,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name="GARDENA smart local",
        )
        self._entry_id = entry_id
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
        self._includable_events: dict[str, Event] = {}
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
        if self._includable_timeouts:
            _LOGGER.debug(
                "Cancelling %d pending includable device timeouts",
                len(self._includable_timeouts),
            )
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

    async def _do_discovery(self) -> None:
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
        _LOGGER.debug(
            "Includable device %s heartbeat timed out, removing issue", instance_id
        )
        self._includable_events.pop(instance_id, None)
        self._includable_timeouts.pop(instance_id, None)
        async_delete_issue(self.hass, DOMAIN, f"include_{instance_id}")

    async def _handle_includable_event(self, event: Event) -> None:
        instance_id = event.entity.path.object_instance_id

        if event.op == "delete":
            _LOGGER.debug(
                "Includable device %s delete received, cancelling timeout", instance_id
            )
            handle = self._includable_timeouts.pop(instance_id, None)
            if handle is not None:
                handle.cancel()
            self._includable_events.pop(instance_id, None)
            async_delete_issue(self.hass, DOMAIN, f"include_{instance_id}")
            return

        is_new = instance_id not in self._includable_events

        # Always reschedule the heartbeat timeout
        handle = self._includable_timeouts.pop(instance_id, None)
        if handle is not None:
            handle.cancel()
        self._includable_timeouts[instance_id] = self.hass.loop.call_later(
            INCLUDABLE_DEVICE_HEARTBEAT_TIMEOUT,
            self._expire_includable,
            instance_id,
        )

        if not is_new:
            _LOGGER.debug(
                "Includable device %s heartbeat, rescheduled timeout", instance_id
            )
            return

        self._includable_events[instance_id] = event
        identifier = event.payload.get("identifier", {}).get("vs", instance_id)

        try:
            info = parse_sgtin96(identifier)
            name = await info.get_model_name()
            device_name = f"{name} {info.serial:08d}"
        except (ValueError, Exception):
            device_name = identifier

        _LOGGER.debug(
            "Includable device %s discovered (%s), creating issue and scheduling timeout",
            instance_id,
            device_name,
        )
        _LOGGER.info("Discovered includable device: %s", device_name)

        async_create_issue(
            self.hass,
            DOMAIN,
            f"include_{instance_id}",
            is_fixable=True,
            severity=IssueSeverity.WARNING,
            translation_key="new_includable_device",
            translation_placeholders={"device_name": device_name},
            data={
                "entry_id": self._entry_id,
                "instance_id": instance_id,
                "identifier": identifier,
                "device_name": device_name,
            },
        )

    async def async_include_device(self, instance_id: str) -> bool:
        event = self._includable_events.get(instance_id)
        if event is None:
            _LOGGER.error(
                "No includable device event found for instance %s", instance_id
            )
            return False

        if not self._ws:
            _LOGGER.error("WebSocket not connected")
            return False

        request = build_inclusion_obj(event.entity.service, instance_id)
        request_id = request[0].request_id

        future: asyncio.Future[Reply] = self.hass.loop.create_future()
        self._pending_replies[request_id] = future

        try:
            await self._ws.send_str(request.model_dump_json())
            _LOGGER.debug("Sent include request for device %s", instance_id)
            reply = await asyncio.wait_for(future, timeout=INCLUDE_REPLY_TIMEOUT)
        except asyncio.TimeoutError:
            _LOGGER.error(
                "Timeout waiting for inclusion reply for device %s", instance_id
            )
            self._pending_replies.pop(request_id, None)
            return False
        except Exception as err:
            _LOGGER.error("Error including device %s: %s", instance_id, err)
            self._pending_replies.pop(request_id, None)
            return False

        if reply.success:
            _LOGGER.debug(
                "Includable device %s included successfully, deleting issue"
                " (heartbeat timeout will clean up remaining state)",
                instance_id,
            )
            async_delete_issue(self.hass, DOMAIN, f"include_{instance_id}")

        return reply.success

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
