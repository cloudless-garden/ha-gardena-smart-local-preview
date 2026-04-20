import logging

import voluptuous as vol


from homeassistant.config_entries import (
    ConfigEntry,
    ConfigEntryChange,
    ConfigSubentry,
    SIGNAL_CONFIG_ENTRY_CHANGED,
    SOURCE_IMPORT,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.const import (
    CONF_HOST,
    CONF_PORT,
    CONF_PASSWORD,
    EVENT_HOMEASSISTANT_STOP,
    Platform,
)
import homeassistant.helpers.config_validation as cv

from . import config_flow as config_flow
from .const import DEFAULT_PORT, DOMAIN
from .coordinator import GardenaSmartLocalCoordinator

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.LAWN_MOWER,
    Platform.NUMBER,
    Platform.SENSOR,
    Platform.SWITCH,
    Platform.VALVE,
]
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
    hass.async_create_task(
        hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": SOURCE_IMPORT},
            data={
                CONF_HOST: conf[CONF_HOST],
                CONF_PORT: conf[CONF_PORT],
                CONF_PASSWORD: conf[CONF_PASSWORD],
            },
        )
    )
    return True


def _async_migrate_devices_to_subentries(
    hass: HomeAssistant, entry: ConfigEntry
) -> None:
    dev_reg = dr.async_get(hass)
    for dev_entry in dr.async_entries_for_config_entry(dev_reg, entry.entry_id):
        if None not in dev_entry.config_entries_subentries[entry.entry_id]:
            continue

        device_id = next(
            (id_ for domain, id_ in dev_entry.identifiers if domain == DOMAIN),
            None,
        )
        if device_id is None:
            _LOGGER.warning(
                "Device %s linked to entry without %s identifier; skipping",
                dev_entry.id,
                DOMAIN,
            )
            continue

        subentry = next(
            (
                se
                for se in entry.subentries.values()
                if se.data.get("device_id") == device_id
            ),
            None,
        )
        if subentry is None:
            title = (
                f"{dev_entry.model} {dev_entry.serial_number}"
                if dev_entry.model and dev_entry.serial_number
                else device_id
            )
            subentry = ConfigSubentry(
                data={"device_id": device_id},
                subentry_type="device",
                title=title,
                unique_id=device_id,
            )
            hass.config_entries.async_add_subentry(entry, subentry)

        dev_reg.async_update_device(
            dev_entry.id,
            add_config_entry_id=entry.entry_id,
            add_config_subentry_id=subentry.subentry_id,
            remove_config_entry_id=entry.entry_id,
            remove_config_subentry_id=None,
        )
        _LOGGER.info("Migrated device %s to subentry", device_id)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    hass.data.setdefault(DOMAIN, {})

    _async_migrate_devices_to_subentries(hass, entry)

    coordinator = GardenaSmartLocalCoordinator(
        hass,
        host=entry.data[CONF_HOST],
        port=entry.data[CONF_PORT],
        password=entry.data[CONF_PASSWORD],
    )
    await coordinator.async_connect()
    hass.data[DOMAIN][entry.entry_id] = coordinator

    async def _stop(_event: object) -> None:
        await coordinator.async_disconnect()

    entry.async_on_unload(hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, _stop))

    known_subentries: dict[str, str] = {
        sid: se.data["device_id"]
        for sid, se in entry.subentries.items()
        if "device_id" in se.data
    }

    @callback
    def _on_entry_updated(
        change_type: ConfigEntryChange, changed_entry: ConfigEntry
    ) -> None:
        if (
            change_type != ConfigEntryChange.UPDATED
            or changed_entry.entry_id != entry.entry_id
        ):
            return
        current_ids = set(entry.subentries.keys())
        for subentry_id, device_id in list(known_subentries.items()):
            if subentry_id not in current_ids:
                del known_subentries[subentry_id]
                hass.async_create_background_task(
                    coordinator.async_exclude_device(device_id),
                    f"gardena_exclude_{device_id}",
                )
        for sid, se in entry.subentries.items():
            if sid not in known_subentries and "device_id" in se.data:
                known_subentries[sid] = se.data["device_id"]

    entry.async_on_unload(
        async_dispatcher_connect(hass, SIGNAL_CONFIG_ENTRY_CHANGED, _on_entry_updated)
    )

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    coordinator: GardenaSmartLocalCoordinator = hass.data[DOMAIN].pop(entry.entry_id)
    await coordinator.async_disconnect()
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
