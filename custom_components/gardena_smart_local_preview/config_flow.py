# SPDX-FileCopyrightText: 2026 GARDENA GmbH
#
# SPDX-License-Identifier: Apache-2.0

import asyncio
import logging
from collections.abc import Mapping
from typing import Any

import aiohttp
import voluptuous as vol
from gardena_smart_local_api.client import (
    AuthenticationError,
    ConfigApiError,
    GatewayClient,
    GatewayConfigApi,
    fetch_certificate,
    hostname_from_certificate,
)
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    ConfigSubentryFlow,
    SubentryFlowResult,
)
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_PORT
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.service_info.zeroconf import ZeroconfServiceInfo
from homeassistant.helpers.typing import ConfigType
from yarl import URL

from .const import CONF_CLOUD_CONNECTION, DEFAULT_PORT, DOMAIN
from .coordinator import GardenaSmartLocalCoordinator

_LOGGER = logging.getLogger(__name__)

# A host pasted with surrounding whitespace is rejected by yarl; trim it in
# one place so every step stores and connects to the clean value.
# vol.Strip keeps the form schema serializable for the frontend.
_HOST = vol.All(str, vol.Strip)


class GardenaSmartLocalConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    @classmethod
    @callback
    def async_get_supported_subentry_types(
        cls, config_entry: ConfigEntry
    ) -> dict[str, type[ConfigSubentryFlow]]:
        return {"device": GardenaInclusionSubentryFlow}

    def __init__(self) -> None:
        self._discovered_host: str | None = None
        self._discovered_port: int = DEFAULT_PORT

    async def async_step_user(self, user_input: dict | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            host = user_input[CONF_HOST]
            unique_id = (
                await async_extract_hostname_from_cert(host, user_input[CONF_PORT])
                or host
            )
            await self.async_set_unique_id(unique_id)
            self._abort_if_unique_id_configured()
            # An entry added the other way round (zeroconf vs. manual), or one
            # created before the gateway certificate carried its name, uses the
            # host as its unique_id, so also match on host.
            self._async_abort_entries_match({CONF_HOST: host})

            error = await _async_try_connect(
                self.hass,
                host,
                user_input[CONF_PORT],
                user_input[CONF_PASSWORD],
            )
            if error:
                errors["base"] = error
            else:
                return self.async_create_entry(title=unique_id, data=user_input)

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_HOST): _HOST,
                    vol.Optional(CONF_PORT, default=DEFAULT_PORT): cv.port,
                    vol.Optional(CONF_PASSWORD, default=""): str,
                }
            ),
            errors=errors,
        )

    async def async_step_zeroconf(
        self, discovery_info: ZeroconfServiceInfo
    ) -> ConfigFlowResult:
        name = discovery_info.hostname.removesuffix(".local.")
        host = discovery_info.host
        port = discovery_info.port or DEFAULT_PORT

        await self.async_set_unique_id(name)
        self._abort_if_unique_id_configured(updates={CONF_HOST: host, CONF_PORT: port})
        # A manually-added entry for the same host would have a different
        # (host based) unique_id, so also match on host.
        self._async_abort_entries_match({CONF_HOST: host})

        self._discovered_host = host
        self._discovered_port = port
        self.context["title_placeholders"] = {"name": name, "host": host}

        return await self.async_step_discovery_confirm()

    async def async_step_discovery_confirm(
        self, user_input: dict | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            error = await _async_try_connect(
                self.hass,
                user_input[CONF_HOST],
                user_input[CONF_PORT],
                user_input.get(CONF_PASSWORD, ""),
            )
            if error:
                errors["base"] = error
            else:
                return self.async_create_entry(
                    title=self.context["title_placeholders"]["name"],
                    data=user_input,
                )

        return self.async_show_form(
            step_id="discovery_confirm",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_HOST, default=self._discovered_host): _HOST,
                    vol.Optional(CONF_PORT, default=self._discovered_port): cv.port,
                    vol.Optional(CONF_PASSWORD, default=""): str,
                }
            ),
            description_placeholders={
                "name": self.context["title_placeholders"]["name"],
            },
            errors=errors,
        )

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        entry = self._get_reauth_entry()

        if user_input is not None:
            error = await _async_try_connect(
                self.hass,
                entry.data[CONF_HOST],
                entry.data[CONF_PORT],
                user_input[CONF_PASSWORD],
            )
            if error:
                errors["base"] = error
            else:
                return self.async_update_reload_and_abort(
                    entry, data_updates={CONF_PASSWORD: user_input[CONF_PASSWORD]}
                )

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({vol.Required(CONF_PASSWORD): str}),
            description_placeholders={"name": entry.title},
            errors=errors,
        )

    async def async_step_reconfigure(
        self, user_input: dict | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        entry = self._get_reconfigure_entry()

        if user_input is not None:
            if user_input[CONF_HOST] != entry.data.get(CONF_HOST):
                # Only a changed host can collide, and only with a different
                # entry: matching the current one would abort every save.
                self._async_abort_entries_match({CONF_HOST: user_input[CONF_HOST]})
            error = await _async_try_connect(
                self.hass,
                user_input[CONF_HOST],
                user_input[CONF_PORT],
                user_input.get(CONF_PASSWORD, ""),
            )
            if not error and CONF_CLOUD_CONNECTION in user_input:
                error = await _async_set_cloud_connection(
                    self.hass,
                    user_input[CONF_HOST],
                    user_input.get(CONF_PASSWORD, ""),
                    user_input[CONF_CLOUD_CONNECTION],
                )
            if error:
                errors["base"] = error
            else:
                unique_id = (
                    await async_extract_hostname_from_cert(
                        user_input[CONF_HOST], user_input[CONF_PORT]
                    )
                    or entry.unique_id
                )
                return self.async_update_reload_and_abort(
                    entry, data=user_input, unique_id=unique_id
                )

        schema: dict[Any, Any] = {
            vol.Required(CONF_HOST, default=entry.data.get(CONF_HOST, "")): _HOST,
            vol.Optional(
                CONF_PORT, default=entry.data.get(CONF_PORT, DEFAULT_PORT)
            ): cv.port,
            vol.Optional(CONF_PASSWORD, default=entry.data.get(CONF_PASSWORD, "")): str,
        }
        # Offer the setting only with the state the gateway has right now. A
        # guessed default would change the setting when the form is saved.
        cloud_connection = await _async_get_cloud_connection(
            self.hass, entry.data[CONF_HOST], entry.data.get(CONF_PASSWORD, "")
        )
        if cloud_connection is not None:
            schema[vol.Optional(CONF_CLOUD_CONNECTION, default=cloud_connection)] = bool

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=vol.Schema(schema),
            errors=errors,
        )

    async def async_step_import(self, import_data: ConfigType) -> ConfigFlowResult:
        import_data[CONF_HOST] = _HOST(import_data[CONF_HOST])
        await self.async_set_unique_id(import_data[CONF_HOST])
        self._abort_if_unique_id_configured()
        return self.async_create_entry(title="GARDENA smart local", data=import_data)


async def _async_try_connect(
    hass: HomeAssistant, host: str, port: int, password: str
) -> str | None:
    try:
        # yarl rejects a host that is empty or contains spaces/control chars.
        URL.build(scheme="wss", host=host, port=port)
    except ValueError:
        _LOGGER.debug("Invalid host %r", host)
        return "invalid_host"

    client = GatewayClient(host, port, password, session=async_get_clientsession(hass))
    try:
        # The client's own timeout also covers a discovery, which this probe
        # never runs, so an unreachable host would wait much longer than needed.
        async with asyncio.timeout(10):
            await client.connect()
    except AuthenticationError:
        return "invalid_auth"
    except (aiohttp.ClientError, TimeoutError, OSError):
        _LOGGER.debug("Error connecting to %s:%s", host, port, exc_info=True)
        return "cannot_connect"
    except Exception:
        _LOGGER.exception("Unexpected error connecting to %s:%s", host, port)
        return "unknown"

    await client.disconnect()
    return None


def _config_api(hass: HomeAssistant, host: str, password: str) -> GatewayConfigApi:
    return GatewayConfigApi(host, password, session=async_get_clientsession(hass))


async def _async_get_cloud_connection(
    hass: HomeAssistant, host: str, password: str
) -> bool | None:
    try:
        return await _config_api(hass, host, password).get_cloud_connection()
    except (AuthenticationError, ConfigApiError, ValueError):
        _LOGGER.debug("Could not read the cloud connection of %s", host, exc_info=True)
        return None


async def _async_set_cloud_connection(
    hass: HomeAssistant, host: str, password: str, enabled: bool
) -> str | None:
    try:
        await _config_api(hass, host, password).set_cloud_connection(enabled)
    except AuthenticationError:
        return "invalid_auth"
    except ConfigApiError:
        _LOGGER.debug(
            "Could not change the cloud connection of %s", host, exc_info=True
        )
        return "cloud_connection_failed"
    return None


async def async_extract_hostname_from_cert(host: str, port: int) -> str | None:
    """Return the hostname taken from its TLS certificate.

    The gateway certificate lists its mDNS hostname (``GARDENA-xxxxxx.local``) as a
    DNS name in the subjectAltName. That name is derived from the gateway's MAC address
    and survives a certificate regeneration, which makes it a stable unique_id
    that a manual and a discovered flow agree on. Return ``None`` when the
    gateway is unreachable or runs firmware whose certificate has no such name.
    """
    try:
        certificate = await fetch_certificate(host, port)
    except (OSError, TimeoutError, ValueError):
        _LOGGER.debug("Could not read the certificate of %s:%s", host, port)
        return None

    return hostname_from_certificate(certificate)


class GardenaInclusionSubentryFlow(ConfigSubentryFlow):
    async def async_step_user(
        self, user_input: dict | None = None
    ) -> SubentryFlowResult:
        if user_input is not None:
            return await self.async_step_select()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({}),
            last_step=False,
        )

    async def async_step_select(
        self, user_input: dict | None = None
    ) -> SubentryFlowResult:
        entry = self._get_entry()
        coordinator: GardenaSmartLocalCoordinator = entry.runtime_data
        devices = {k: v.device_name for k, v in coordinator.includable_devices.items()}

        if not devices:
            return self.async_abort(reason="no_devices_found")

        errors: dict[str, str] = {}

        if user_input is not None:
            instance_id = user_input["device"]
            device_id = await coordinator.async_include_device(instance_id)
            if device_id is not None:
                result = self.async_create_entry(
                    title=devices[instance_id],
                    data={"device_id": device_id},
                    unique_id=device_id,
                )
                # Broadcast coordinator update after _async_finish_flow adds the
                # subentry to entry.subentries, so _add_new_devices sees it.
                self.hass.loop.call_soon(
                    coordinator.async_set_updated_data, coordinator.data
                )
                return result
            errors["base"] = "inclusion_failed"

        return self.async_show_form(
            step_id="select",
            data_schema=vol.Schema({vol.Required("device"): vol.In(devices)}),
            errors=errors,
        )
