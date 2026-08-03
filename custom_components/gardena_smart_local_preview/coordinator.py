# SPDX-FileCopyrightText: 2026 GARDENA GmbH
#
# SPDX-License-Identifier: Apache-2.0

import asyncio
import base64
import logging
from dataclasses import dataclass

import aiohttp
from gardena_smart_local_api.devices import (
    Device,
    DeviceMap,
    build_discovery_obj,
    build_inclusion_obj,
    create_devices_from_messages,
)
from gardena_smart_local_api.messages import (
    EgressMessageList,
    Event,
    IngressMessageList,
    Reply,
)
from gardena_smart_local_api.sgtin96 import SGTIN96Info
from gardena_smart_local_api.utils import deep_merge_dict
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util.ssl import get_default_no_verify_context
from yarl import URL

INCLUDE_REPLY_TIMEOUT = 10
EXCLUDE_REPLY_TIMEOUT = 10
INCLUDABLE_DEVICE_HEARTBEAT_TIMEOUT = 25
INCLUSION_TIMEOUT = 30
FIRMWARE_REPLY_TIMEOUT = 10
COMMAND_REPLY_TIMEOUT = 10
# A device included outside our own inclusion flow (e.g. via the official
# app while we're already connected) arrives as a burst of ordinary events
# for a device_id we don't know yet. Debounce before re-running discovery so
# one burst triggers one discovery, not one per event.
UNKNOWN_DEVICE_DISCOVERY_DEBOUNCE = 3


@dataclass
class IncludableDeviceInfo:
    instance_id: str
    service: str
    device_id: str
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
        self.uri = URL.build(scheme="wss", host=host, port=port)

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
        self._first_connect_result: asyncio.Future[None] | None = None
        # Devices with a command reply still outstanding. While a device is
        # in here, incoming Events for it are merged into self._devices but
        # not broadcast — the gateway reports state changes (e.g. a valve
        # opening) across several back-to-back frames, each of which would
        # otherwise flash an intermediate state in the UI. The final,
        # confirmed state is broadcast once the reply for the last
        # outstanding command on that device arrives (see send_request).
        self._pending_reply_devices: dict[str, int] = {}
        self._unknown_device_discovery_handle: asyncio.TimerHandle | None = None

    async def _async_update_data(self) -> DeviceMap:
        return self._devices

    @property
    def connected(self) -> bool:
        """Return True if the WebSocket to the gateway is currently connected."""
        return self._ws is not None and not self._ws.closed

    async def async_connect(self) -> None:
        if self._ssl_context is None:
            self._ssl_context = get_default_no_verify_context()
        self._first_connect_result = self.hass.loop.create_future()
        self._task = self.hass.async_create_background_task(
            self._ws_loop(), "gardena_smart_local_preview_websocket"
        )
        async with asyncio.timeout(15):
            await self._first_connect_result

    async def async_disconnect(self) -> None:
        for handle in self._includable_timeouts.values():
            handle.cancel()
        self._includable_timeouts.clear()
        if self._unknown_device_discovery_handle is not None:
            self._unknown_device_discovery_handle.cancel()
            self._unknown_device_discovery_handle = None
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
                _LOGGER.debug("Connecting to GARDENA smart Gateway at %s", self.uri)
                async with (
                    aiohttp.ClientSession() as session,
                    session.ws_connect(
                        self.uri,
                        ssl=self._ssl_context,
                        heartbeat=30,
                        headers={"Authorization": f"Basic {self.auth_b64}"},
                    ) as ws,
                ):
                    self._ws = ws
                    _LOGGER.info("Connected to GARDENA smart Gateway at %s", self.uri)

                    reader_task = self.hass.async_create_background_task(
                        self._ws_reader(ws),
                        "gardena_smart_local_preview_ws_reader",
                    )
                    consumer_task = self.hass.async_create_background_task(
                        self._msg_consumer(),
                        "gardena_smart_local_preview_msg_consumer",
                    )

                    await self._do_discovery()

                    if (
                        self._first_connect_result
                        and not self._first_connect_result.done()
                    ):
                        self._first_connect_result.set_result(None)

                    # Block until either worker exits (disconnect / error), then
                    # re-raise its exception, if any, so we reconnect below.
                    done, _pending = await asyncio.wait(
                        (reader_task, consumer_task),
                        return_when=asyncio.FIRST_COMPLETED,
                    )
                    for task in done:
                        task.result()
                    _LOGGER.info(
                        "Disconnected from GARDENA smart Gateway, reconnecting"
                    )

            except asyncio.CancelledError:
                _LOGGER.debug("WebSocket loop cancelled")
                if self._first_connect_result and not self._first_connect_result.done():
                    self._first_connect_result.cancel()
                break
            except Exception as err:  # noqa: BLE001 - any transport error must trigger a reconnect
                if self._first_connect_result and not self._first_connect_result.done():
                    self._first_connect_result.set_exception(err)
                _LOGGER.error("WebSocket error: %s", err)
                await asyncio.sleep(5)
            finally:
                self._ws = None
                for task in (reader_task, consumer_task):
                    if task and not task.done():
                        task.cancel()
                        try:
                            await task
                        except (asyncio.CancelledError, Exception) as err:  # noqa: BLE001 - best-effort cleanup, cancellation is expected
                            _LOGGER.debug("Error awaiting cancelled task: %s", err)
                # Cancel any pending reply futures so waiters don't hang
                for fut in self._pending_replies.values():
                    if not fut.done():
                        fut.cancel()
                self._pending_replies.clear()
                self._pending_reply_devices.clear()
                # Let entities re-check availability now that we're disconnected.
                self.async_update_listeners()

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
        _LOGGER.warning(
            "Connection to GARDENA smart Gateway closed (close code: %s)", ws.close_code
        )

    async def _msg_consumer(self) -> None:
        try:
            while True:
                raw = await self._msg_queue.get()
                try:
                    messages = IngressMessageList.model_validate_json(raw)
                except Exception:  # noqa: BLE001 - malformed message, ignore and keep reading
                    _LOGGER.debug(
                        "Ignoring non-list message from GARDENA smart Gateway: %s", raw
                    )
                    continue

                passthrough: IngressMessageList = IngressMessageList([])
                for msg in messages:
                    if (
                        isinstance(msg, Reply)
                        and msg.request_id in self._pending_replies
                    ):
                        fut = self._pending_replies.pop(msg.request_id)
                        if not fut.done():
                            fut.set_result(msg)
                    else:
                        passthrough.append(msg)

                if passthrough:
                    await self._handle_messages(passthrough)
        except asyncio.CancelledError:
            raise
        except Exception:
            _LOGGER.exception(
                "Message consumer failed, incoming events are no longer processed"
            )
            raise

    async def _do_discovery(self, broadcast: bool = True) -> None:
        discovery = build_discovery_obj()
        n = len(list(discovery))
        _LOGGER.debug(
            "Sent discovery request to GARDENA smart Gateway, awaiting %d replies", n
        )

        try:
            replies = await self.send_request(
                "discovery", discovery, wait_for_response_sec=30
            )
        except TimeoutError:
            raise RuntimeError(
                f"Timed out waiting for discovery replies from GARDENA smart Gateway (expected {n})"
            )

        devices = await create_devices_from_messages(replies)
        self._update_devices(devices)
        if broadcast:
            self.async_set_updated_data(self._devices)
        _LOGGER.info("Discovery complete, found %d device(s)", len(self._devices))

    def _schedule_unknown_device_discovery(self, device_id: str) -> None:
        if self._unknown_device_discovery_handle is not None:
            self._unknown_device_discovery_handle.cancel()
        _LOGGER.debug("Event for unknown device %s, scheduling re-discovery", device_id)
        self._unknown_device_discovery_handle = self.hass.loop.call_later(
            UNKNOWN_DEVICE_DISCOVERY_DEBOUNCE,
            lambda: self.hass.async_create_task(self._discover_unknown_devices()),
        )

    async def _discover_unknown_devices(self) -> None:
        self._unknown_device_discovery_handle = None
        _LOGGER.info("Re-running discovery to pick up newly included device(s)")
        try:
            await self._do_discovery()
        except Exception as err:  # noqa: BLE001 - best-effort, don't crash the coordinator
            _LOGGER.warning("Re-discovery for unknown device(s) failed: %s", err)

    async def _handle_messages(self, messages: IngressMessageList) -> None:
        try:
            _LOGGER.debug("Handling %d message(s)", len(messages))

            updated_device_ids: set[str] = set()

            for msg in messages:
                if isinstance(msg, Event):
                    if msg.entity.path.object_name == "includable_device":
                        await self._handle_includable_event(msg)
                    elif msg.entity.device:
                        device_id = msg.entity.device
                        if (
                            msg.op == "delete"
                            and msg.entity.path.object_name is None
                            and device_id in self._devices
                        ):
                            _LOGGER.info("Device %s removed (delete event)", device_id)
                            self.async_drop_device(device_id)
                        elif device_id in self._devices:
                            _LOGGER.debug(
                                "Updating device %s with event: %s",
                                device_id,
                                msg,
                            )
                            device = self._devices[device_id]
                            was_online = device.is_online
                            device.update_data(msg)
                            if device.is_online != was_online:
                                _LOGGER.info(
                                    "Device %s connection status changed: online=%s",
                                    device_id,
                                    device.is_online,
                                )
                            updated_device_ids.add(device_id)
                        elif msg.op != "delete":
                            # A device we don't know yet, e.g. included via
                            # the official app while we were already
                            # connected. Not a delete op, so it's not just a
                            # leftover event for an already-excluded device.
                            self._schedule_unknown_device_discovery(device_id)
                    else:
                        _LOGGER.debug(
                            "Event does not have device ID, ignoring: %s", msg
                        )

            # Devices with a command in flight are merged above but not
            # broadcast yet — send_request() flushes them once the reply for
            # that command confirms the settled state.
            if updated_device_ids - self._pending_reply_devices.keys():
                self.async_set_updated_data(self._devices)

        except Exception as err:  # noqa: BLE001 - one bad message must not crash the coordinator
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

        identifier = event.payload.get("identifier", {}).get("vs")
        if identifier is None:
            _LOGGER.debug(
                "Includable event for %s lacks identifier, ignoring", instance_id
            )
            return
        try:
            sgtin = SGTIN96Info.from_hex(identifier)
        except ValueError:
            _LOGGER.debug(
                "Includable device %s has unparseable identifier %s, ignoring",
                instance_id,
                identifier,
            )
            return
        device_name = f"{await sgtin.get_model_name()} {sgtin.serial:08d}"

        self._includable_devices[instance_id] = IncludableDeviceInfo(
            instance_id=instance_id,
            service=service,
            device_id=identifier,
            device_name=device_name,
        )
        _LOGGER.info(
            "Discovered includable device: %s (%s, instance %s)",
            identifier,
            device_name,
            instance_id,
        )

    @property
    def includable_devices(self) -> dict[str, IncludableDeviceInfo]:
        return dict(self._includable_devices)

    async def async_include_device(self, instance_id: str) -> str | None:
        info = self._includable_devices.get(instance_id)
        if info is None:
            _LOGGER.error("No includable device with instance_id %s", instance_id)
            return None
        device_id = info.device_id

        request = build_inclusion_obj(info.service, instance_id)
        try:
            replies = await self.send_request(
                instance_id, request, wait_for_response_sec=INCLUDE_REPLY_TIMEOUT
            )
        except TimeoutError:
            _LOGGER.error("Timeout waiting for inclusion reply for %s", device_id)
            return None
        except Exception as err:  # noqa: BLE001 - report failure to the config flow instead of raising
            _LOGGER.error("Error including device %s: %s", instance_id, err)
            return None

        for msg in replies:
            if isinstance(msg, Reply) and msg.success:
                for _ in range(INCLUSION_TIMEOUT):
                    if instance_id not in self._includable_devices:
                        break
                    await asyncio.sleep(1)
                else:
                    _LOGGER.error(
                        "Timeout waiting for inclusion to complete for %s", device_id
                    )
                    return None
                _LOGGER.info(
                    "Device %s (instance %s) included successfully",
                    info.device_id,
                    instance_id,
                )
                try:
                    # broadcast=False: the subentry doesn't exist yet at this
                    # point; the caller schedules async_set_updated_data as a
                    # task so it runs after _async_finish_flow adds the subentry.
                    await self._do_discovery(broadcast=False)
                except Exception as err:  # noqa: BLE001 - inclusion already succeeded, don't fail it over this
                    _LOGGER.warning("Re-discovery after inclusion failed: %s", err)
                    return None
                if info.device_id not in self._devices:
                    _LOGGER.warning(
                        "Included device %s not found in discovery", info.device_id
                    )
                    return None
                return info.device_id

        _LOGGER.error("Inclusion of device %s failed", info.device_id)
        return None

    @callback
    def async_drop_device(self, device_id: str) -> None:
        if self._devices.pop(device_id, None) is not None:
            _LOGGER.debug("Dropped device %s from coordinator", device_id)
            self.async_set_updated_data(self._devices)

    async def async_exclude_device(self, device_id: str) -> bool:
        device = self._devices.get(device_id)
        if device is None:
            _LOGGER.error("No device with id %s", device_id)
            return False

        request = device.build_exclusion_obj()
        # Drop the device locally before requesting exclusion so the inbound
        # delete event during factory reset cannot resurrect it via
        # downstream listeners (e.g. subentry auto-creation).
        self.async_drop_device(device_id)
        try:
            replies = await self.send_request(
                device_id, request, wait_for_response_sec=EXCLUDE_REPLY_TIMEOUT
            )
        except TimeoutError:
            _LOGGER.error("Timeout waiting for exclusion reply for %s", device_id)
            return False
        except Exception as err:  # noqa: BLE001 - report failure to the config flow instead of raising
            _LOGGER.error("Error excluding device %s: %s", device_id, err)
            return False

        for msg in replies:
            if isinstance(msg, Reply) and msg.success:
                _LOGGER.info("Device %s excluded successfully", device_id)
                return True

        _LOGGER.error("Exclusion of device %s failed", device_id)
        return False

    async def async_refresh_firmware(self, device_id: str) -> None:
        device = self._devices.get(device_id)
        if device is None:
            return

        request = (
            device.build_refresh_available_firmware_version_obj()
            + device.build_refresh_firmware_update_state_obj()
        )
        try:
            replies = await self.send_request(
                device_id, request, wait_for_response_sec=FIRMWARE_REPLY_TIMEOUT
            )
        except TimeoutError:
            _LOGGER.debug("Timeout refreshing firmware state for %s", device_id)
            return
        except Exception as err:  # noqa: BLE001 - best-effort refresh, must not disrupt the coordinator
            _LOGGER.debug("Error refreshing firmware state for %s: %s", device_id, err)
            return

        updated = False
        for msg in replies:
            if isinstance(msg, Reply) and msg.success and msg.payload:
                data = msg.payload.get(device_id)
                if data:
                    deep_merge_dict(device.data, data)
                    updated = True
        if updated:
            self.async_set_updated_data(self._devices)

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
            for device_id in self._devices.keys() - devices.keys():
                _LOGGER.info(
                    "Device %s no longer present in discovery, dropping", device_id
                )
                del self._devices[device_id]
            for device in devices.values():
                self._update_device(device)
        except Exception as err:  # noqa: BLE001 - one bad device must not stop the discovery update
            _LOGGER.warning("Failed to update devices: %s", err)

    async def send_request(
        self,
        device_id: str,
        request: EgressMessageList,
        wait_for_response_sec: float = 0,
    ) -> IngressMessageList:
        if not self._ws or self._ws.closed:
            raise HomeAssistantError(
                f"Cannot send request to device {device_id}: WebSocket not connected"
            )

        if wait_for_response_sec > 0:
            loop = asyncio.get_running_loop()
            pending_ids = {
                req.request_id for req in request.root if req.request_id is not None
            }
            futures: dict[str, asyncio.Future[Reply]] = {
                rid: loop.create_future() for rid in pending_ids
            }
            self._pending_replies.update(futures)
            self._pending_reply_devices[device_id] = (
                self._pending_reply_devices.get(device_id, 0) + 1
            )

            try:
                await self._ws.send_str(request.model_dump_json())
                _LOGGER.debug("Sent request to device %s: %s", device_id, request)

                try:
                    async with asyncio.timeout(wait_for_response_sec):
                        replies = await asyncio.gather(*futures.values())
                except TimeoutError:
                    for rid in pending_ids:
                        self._pending_replies.pop(rid, None)
                    raise

                return IngressMessageList(list(replies))
            finally:
                remaining = self._pending_reply_devices.get(device_id, 1) - 1
                if remaining <= 0:
                    self._pending_reply_devices.pop(device_id, None)
                    # Last outstanding command for this device settled —
                    # broadcast the confirmed state now.
                    self.async_set_updated_data(self._devices)
                else:
                    self._pending_reply_devices[device_id] = remaining

        await self._ws.send_str(request.model_dump_json())
        _LOGGER.debug("Sent request to device %s: %s", device_id, request)
        return IngressMessageList([])
