from __future__ import annotations

from homeassistant import config_entries
from homeassistant.components.bluetooth import BluetoothServiceInfoBleak
from .const import DOMAIN

class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_bluetooth(self, discovery_info: BluetoothServiceInfoBleak):
        await self.async_set_unique_id(discovery_info.address)
        self._abort_if_unique_id_configured()
        title = discovery_info.name or "Pwnagotchi"
        return self.async_create_entry(title=title, data={"address": discovery_info.address})
