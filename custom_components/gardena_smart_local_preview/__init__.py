import logging

import voluptuous as vol

from homeassistant.core import HomeAssistant
from homeassistant.const import (
    CONF_HOST,
    CONF_PORT,
    CONF_PASSWORD,
    EVENT_HOMEASSISTANT_STOP,
    Platform,
)
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers import discovery

from .const import DEFAULT_PORT, DOMAIN
from .coordinator import GardenaSmartLocalCoordinator

PLATFORMS: list[Platform] = [Platform.VALVE]
_LOGGER = logging.getLogger(__name__)

CONFIG_SCHEMA = vol.Schema(
    {
        DOMAIN: vol.Schema(
            {
                vol.Required(CONF_HOST): cv.string,
                vol.Optional(CONF_PORT, default=DEFAULT_PORT): cv.port,
                vol.Optional(CONF_PASSWORD, default=""): cv.string,
            }
        )
    },
    extra=vol.ALLOW_EXTRA,
)


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    hass.data.setdefault(DOMAIN, {})

    if DOMAIN not in config:
        return True

    conf = config[DOMAIN]
    coordinator = GardenaSmartLocalCoordinator(
        hass,
        host=conf[CONF_HOST],
        port=conf[CONF_PORT],
        password=conf[CONF_PASSWORD],
    )
    await coordinator.async_connect()

    hass.data[DOMAIN]["yaml"] = coordinator

    async def _stop(_event: object) -> None:
        await coordinator.async_disconnect()

    hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, _stop)

    for platform in PLATFORMS:
        hass.async_create_task(
            discovery.async_load_platform(hass, platform, DOMAIN, {}, config)
        )

    return True
