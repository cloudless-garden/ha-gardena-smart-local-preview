# SPDX-FileCopyrightText: 2026 GARDENA GmbH
#
# SPDX-License-Identifier: Apache-2.0

import asyncio
import logging
from dataclasses import dataclass

from gardena_smart_local_api.client import GatewayClient, RequestError
from gardena_smart_local_api.devices import Device, DeviceMap, build_inclusion_obj
from gardena_smart_local_api.messages import (
    EgressMessageList,
    Event,
    IngressMessageList,
    Reply,
)
from gardena_smart_local_api.sgtin96 import SGTIN96Info
from gardena_smart_local_api.utils import deep_merge_dict
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

INCLUDE_REPLY_TIMEOUT = 10
EXCLUDE_REPLY_TIMEOUT = 10
INCLUDABLE_DEVICE_HEARTBEAT_TIMEOUT = 25
INCLUSION_TIMEOUT = 30
FIRMWARE_REPLY_TIMEOUT = 10
COMMAND_REPLY_TIMEOUT = 10
DISCOVERY_REPLY_TIMEOUT = 30
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
        # Keeps the connection open and reconnects on its own. After a rejected
        # password it stops instead of hammering the gateway and starts the
        # reauthentication flow, which reloads the entry.
        self.client = GatewayClient(
            host,
            port,
            password,
            session=async_get_clientsession(hass),
            on_connect=self._async_on_connect,
            on_event=self._async_on_event,
            on_disconnect=self._on_disconnect,
            on_auth_failed=self._on_auth_failed,
        )
        self._devices: DeviceMap = DeviceMap({})
        self._includable_devices: dict[str, IncludableDeviceInfo] = {}
        self._includable_timeouts: dict[str, asyncio.TimerHandle] = {}
        # Devices with a command reply still outstanding. While a device is
        # in here, incoming Events for it are merged into self._devices but
        # not broadcast — the gateway reports state changes (e.g. a valve
        # opening) across several back-to-back frames, each of which would
        # otherwise flash an intermediate state in the UI. The final,
        # confirmed state is broadcast once the reply for the last
        # outstanding command on that device arrives (see send_request).
        self._pending_reply_devices: dict[str, int] = {}
        self._unknown_device_discovery_handle: asyncio.TimerHandle | None = None
        # Devices this integration is including right now. Their event burst
        # must not trigger the unknown-device auto-discovery, which could
        # create the subentry before the inclusion flow does.
        self._including_device_ids: set[str] = set()

    async def _async_update_data(self) -> DeviceMap:
        return self._devices

    @property
    def uri(self) -> str:
        return self.client.uri

    @property
    def connected(self) -> bool:
        """Return True if the WebSocket to the gateway is currently connected."""
        return self.client.connected

    async def async_connect(self) -> None:
        await self.client.connect()

    async def async_disconnect(self) -> None:
        for handle in self._includable_timeouts.values():
            handle.cancel()
        self._includable_timeouts.clear()
        if self._unknown_device_discovery_handle is not None:
            self._unknown_device_discovery_handle.cancel()
            self._unknown_device_discovery_handle = None
        await self.client.disconnect()

    @callback
    def _on_auth_failed(self) -> None:
        self.config_entry.async_start_reauth(self.hass)

    async def _async_on_connect(self) -> None:
        """Discover the devices after every (re)connect.

        The first connect only succeeds once this finishes, so a gateway that
        does not answer discovery fails the setup.
        """
        await self._do_discovery()

    @callback
    def _on_disconnect(self) -> None:
        """Let entities re-check their availability once the connection drops."""
        self.async_update_listeners()

    async def _do_discovery(self, broadcast: bool = True) -> None:
        devices = await self.client.discover_devices(DISCOVERY_REPLY_TIMEOUT)
        self._update_devices(devices)
        if broadcast:
            self.async_set_updated_data(self._devices)
        _LOGGER.info("Discovery complete, found %d device(s)", len(self._devices))

    def _schedule_unknown_device_discovery(self, device_id: str) -> None:
        if device_id in self._including_device_ids:
            # We are including this device ourselves; async_include_device
            # runs its own discovery. A parallel auto-discovery could create
            # the subentry before the inclusion flow does.
            return
        if self._unknown_device_discovery_handle is not None:
            # A run is already scheduled; a burst of events for the same
            # unknown device must not keep pushing it back indefinitely.
            return
        _LOGGER.debug("Event for unknown device %s, scheduling re-discovery", device_id)
        self._unknown_device_discovery_handle = self.hass.loop.call_later(
            UNKNOWN_DEVICE_DISCOVERY_DEBOUNCE,
            lambda: self.hass.async_create_task(self._discover_unknown_devices()),
        )

    async def _discover_unknown_devices(self) -> None:
        _LOGGER.info("Re-running discovery to pick up newly included device(s)")
        try:
            await self._do_discovery()
        except Exception as err:  # noqa: BLE001 - best-effort, don't crash the coordinator
            _LOGGER.warning("Re-discovery for unknown device(s) failed: %s", err)
        finally:
            # Keep the marker set until discovery finishes; clearing it earlier
            # lets a continued event burst schedule an overlapping run.
            self._unknown_device_discovery_handle = None

    async def _async_on_event(self, event: Event) -> None:
        try:
            device_id = await self._handle_event(event)
        except Exception as err:  # noqa: BLE001 - one bad event must not stop the rest
            _LOGGER.warning("Error handling event %s: %s", event, err)
            return

        # A device with a command in flight is merged but not broadcast yet:
        # send_request() flushes it once the reply for that command confirms
        # the settled state.
        if device_id is not None and device_id not in self._pending_reply_devices:
            self.async_set_updated_data(self._devices)

    async def _handle_event(self, msg: Event) -> str | None:
        """Apply an event to the device map, returning the device it updated."""
        if msg.entity.path.object_name == "includable_device":
            await self._handle_includable_event(msg)
            return None

        device_id = msg.entity.device
        if not device_id:
            _LOGGER.debug("Event does not have device ID, ignoring: %s", msg)
            return None

        if (
            msg.op == "delete"
            and msg.entity.path.object_name is None
            and device_id in self._devices
        ):
            _LOGGER.info("Device %s removed (delete event)", device_id)
            self.async_drop_device(device_id)
        elif device_id in self._devices:
            _LOGGER.debug("Updating device %s with event: %s", device_id, msg)
            device = self._devices[device_id]
            was_online = device.is_online
            device.update_data(msg)
            if device.is_online != was_online:
                _LOGGER.info(
                    "Device %s connection status changed: online=%s",
                    device_id,
                    device.is_online,
                )
            return device_id
        elif msg.op != "delete":
            # A device we don't know yet, e.g. included via the official app
            # while we were already connected. Not a delete op, so it's not
            # just a leftover event for an already-excluded device.
            self._schedule_unknown_device_discovery(device_id)
        return None

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
        self._including_device_ids.add(device_id)
        try:
            return await self._include_device(instance_id, info)
        finally:
            self._including_device_ids.discard(device_id)

    async def _include_device(
        self, instance_id: str, info: IncludableDeviceInfo
    ) -> str | None:
        device_id = info.device_id
        request = build_inclusion_obj(info.service, instance_id)
        try:
            await self.send_request(
                instance_id, request, wait_for_response_sec=INCLUDE_REPLY_TIMEOUT
            )
        except TimeoutError:
            _LOGGER.error("Timeout waiting for inclusion reply for %s", device_id)
            return None
        except RequestError as err:
            _LOGGER.error("Inclusion of device %s rejected: %s", device_id, err)
            return None
        except Exception as err:  # noqa: BLE001 - report failure to the config flow instead of raising
            _LOGGER.error("Error including device %s: %s", instance_id, err)
            return None

        for _ in range(INCLUSION_TIMEOUT):
            if instance_id not in self._includable_devices:
                break
            await asyncio.sleep(1)
        else:
            _LOGGER.error("Timeout waiting for inclusion to complete for %s", device_id)
            return None
        _LOGGER.info(
            "Device %s (instance %s) included successfully", device_id, instance_id
        )
        try:
            # broadcast=False: the subentry doesn't exist yet at this
            # point; the caller schedules async_set_updated_data as a
            # task so it runs after _async_finish_flow adds the subentry.
            await self._do_discovery(broadcast=False)
        except Exception as err:  # noqa: BLE001 - inclusion already succeeded, don't fail it over this
            _LOGGER.warning("Re-discovery after inclusion failed: %s", err)
            return None
        if device_id not in self._devices:
            _LOGGER.warning("Included device %s not found in discovery", device_id)
            return None
        return device_id

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
            await self.send_request(
                device_id, request, wait_for_response_sec=EXCLUDE_REPLY_TIMEOUT
            )
        except TimeoutError:
            _LOGGER.error("Timeout waiting for exclusion reply for %s", device_id)
            return False
        except RequestError as err:
            _LOGGER.error("Exclusion of device %s rejected: %s", device_id, err)
            return False
        except Exception as err:  # noqa: BLE001 - report failure to the config flow instead of raising
            _LOGGER.error("Error excluding device %s: %s", device_id, err)
            return False

        _LOGGER.info("Device %s excluded successfully", device_id)
        return True

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
        except RequestError as err:
            # One of the requests failed; the others may still have succeeded.
            replies = err.replies
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
        for device_id in self._devices.keys() - devices.keys():
            _LOGGER.info(
                "Device %s no longer present in discovery, dropping", device_id
            )
            del self._devices[device_id]
        for device in devices.values():
            try:
                self._update_device(device)
            except Exception:  # one bad device must not stop the discovery update
                _LOGGER.warning("Failed to update device %s", device.id, exc_info=True)

    async def send_request(
        self,
        device_id: str,
        request: EgressMessageList,
        wait_for_response_sec: float = 0,
    ) -> IngressMessageList:
        """Send a request to the gateway, optionally waiting for its replies.

        Raises `RequestError` if the gateway rejects the request, `TimeoutError`
        if it does not answer in time, and `ConnectionError` if the connection
        is not open or drops.
        """
        if wait_for_response_sec <= 0:
            await self.client.send_request(request, timeout=None)
            _LOGGER.debug("Sent request to device %s: %s", device_id, request)
            return IngressMessageList([])

        self._pending_reply_devices[device_id] = (
            self._pending_reply_devices.get(device_id, 0) + 1
        )
        try:
            _LOGGER.debug("Sending request to device %s: %s", device_id, request)
            return await self.client.send_request(request, wait_for_response_sec)
        finally:
            remaining = self._pending_reply_devices.get(device_id, 1) - 1
            if remaining <= 0:
                self._pending_reply_devices.pop(device_id, None)
                # Last outstanding command for this device settled —
                # broadcast the confirmed state now.
                self.async_set_updated_data(self._devices)
            else:
                self._pending_reply_devices[device_id] = remaining
