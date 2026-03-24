import base64
import logging

import aiohttp
import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.helpers.service_info.zeroconf import ZeroconfServiceInfo
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_PORT
from homeassistant.helpers.typing import ConfigType
from homeassistant.util.ssl import get_default_no_verify_context

from .const import DEFAULT_PORT, DOMAIN

_LOGGER = logging.getLogger(__name__)


class GardenaSmartLocalConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self) -> None:
        self._discovered_host: str | None = None
        self._discovered_port: int = DEFAULT_PORT

    async def async_step_user(self, user_input: dict | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            await self.async_set_unique_id(user_input[CONF_HOST])
            self._abort_if_unique_id_configured()

            error = await _async_try_connect(
                user_input[CONF_HOST],
                user_input[CONF_PORT],
                user_input[CONF_PASSWORD],
            )
            if error:
                errors["base"] = error
            else:
                return self.async_create_entry(
                    title=user_input[CONF_HOST],
                    data=user_input,
                )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_HOST): str,
                    vol.Optional(CONF_PORT, default=DEFAULT_PORT): int,
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
        self._abort_if_unique_id_configured()

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
                    vol.Required(CONF_HOST, default=self._discovered_host): str,
                    vol.Optional(CONF_PORT, default=self._discovered_port): int,
                    vol.Optional(CONF_PASSWORD, default=""): str,
                }
            ),
            description_placeholders={
                "name": self.context["title_placeholders"]["name"],
            },
            errors=errors,
        )

    async def async_step_reconfigure(
        self, user_input: dict | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        entry = self._get_reconfigure_entry()

        if user_input is not None:
            error = await _async_try_connect(
                user_input[CONF_HOST],
                user_input[CONF_PORT],
                user_input.get(CONF_PASSWORD, ""),
            )
            if error:
                errors["base"] = error
            else:
                return self.async_update_reload_and_abort(entry, data=user_input)

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_HOST, default=entry.data.get(CONF_HOST, "")): str,
                    vol.Optional(
                        CONF_PORT, default=entry.data.get(CONF_PORT, DEFAULT_PORT)
                    ): int,
                    vol.Optional(
                        CONF_PASSWORD, default=entry.data.get(CONF_PASSWORD, "")
                    ): str,
                }
            ),
            errors=errors,
        )

    async def async_step_import(self, import_data: ConfigType) -> ConfigFlowResult:
        await self.async_set_unique_id(import_data[CONF_HOST])
        self._abort_if_unique_id_configured()
        return self.async_create_entry(title="GARDENA smart local", data=import_data)


async def _async_try_connect(host: str, port: int, password: str) -> str | None:
    ssl_context = get_default_no_verify_context()

    auth_b64 = base64.b64encode(f"_:{password}".encode()).decode("ascii")

    try:
        async with aiohttp.ClientSession() as session:
            async with session.ws_connect(
                f"wss://{host}:{port}",
                ssl=ssl_context,
                headers={"Authorization": f"Basic {auth_b64}"},
                timeout=aiohttp.ClientTimeout(total=10),
            ) as ws:
                await ws.close()
    except aiohttp.WSServerHandshakeError as err:
        if err.status == 401:
            return "invalid_auth"
        _LOGGER.debug("Handshake error connecting to %s:%s", host, port, exc_info=True)
        return "cannot_connect"
    except (aiohttp.ClientConnectionError, TimeoutError, OSError):
        _LOGGER.debug("Error connecting to %s:%s", host, port, exc_info=True)
        return "cannot_connect"
    except Exception:
        _LOGGER.exception("Unexpected error connecting to %s:%s", host, port)
        return "unknown"

    return None
