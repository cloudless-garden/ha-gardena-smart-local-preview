from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.helpers.typing import ConfigType

from .const import DOMAIN


class GardenaSmartLocalConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_import(self, import_data: ConfigType) -> ConfigFlowResult:
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()
        return self.async_create_entry(title="GARDENA smart local", data=import_data)
