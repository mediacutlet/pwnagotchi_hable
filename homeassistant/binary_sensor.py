from __future__ import annotations

from homeassistant import config_entries
from homeassistant.components.bluetooth.passive_update_processor import (
    PassiveBluetoothDataProcessor,
    PassiveBluetoothDataUpdate,
    PassiveBluetoothProcessorCoordinator,
    PassiveBluetoothProcessorEntity,
)
from homeassistant.components.binary_sensor import BinarySensorEntity, BinarySensorDeviceClass
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN


def _only_charging(update: PassiveBluetoothDataUpdate) -> PassiveBluetoothDataUpdate:
    filt_desc = {k: v for k, v in (update.entity_descriptions or {}).items() if k.key == "charging"}
    filt_data = {k: v for k, v in (update.entity_data or {}).items() if k.key == "charging"}
    filt_names = {k: v for k, v in (update.entity_names or {}).items() if k.key == "charging"}
    return PassiveBluetoothDataUpdate(
        devices=update.devices,
        entity_descriptions=filt_desc,
        entity_data=filt_data,
        entity_names=filt_names,
    )


async def async_setup_entry(
    hass: HomeAssistant,
    entry: config_entries.ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: PassiveBluetoothProcessorCoordinator = hass.data[DOMAIN][entry.entry_id]
    processor = PassiveBluetoothDataProcessor(_only_charging)
    entry.async_on_unload(processor.async_add_entities_listener(PwnagotchiBleChargingBinary, async_add_entities))
    entry.async_on_unload(coordinator.async_register_processor(processor))


class PwnagotchiBleChargingBinary(PassiveBluetoothProcessorEntity, BinarySensorEntity):
    _attr_name = "Pwnagotchi Charging"
    _attr_device_class = BinarySensorDeviceClass.BATTERY_CHARGING

    @property
    def is_on(self) -> bool | None:
        return self.processor.entity_data.get(self.entity_key)
