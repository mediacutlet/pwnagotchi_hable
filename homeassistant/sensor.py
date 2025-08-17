\
from __future__ import annotations
from typing import Any, List, Dict
from homeassistant.components.sensor import SensorEntity, SensorDeviceClass
from homeassistant.const import UnitOfTemperature
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.device_registry import DeviceInfo, CONNECTION_BLUETOOTH
from homeassistant.helpers.dispatcher import async_dispatcher_connect

from .const import DOMAIN
from . import LAST_VALUES, _sig  # type: ignore[attr-defined]

_KEYS: List[str] = [
    "last_seen",
    "handshakes",
    "points",
    "epochs",
    "train_epochs",
    "cpu_temp",
    "age_index",
    "age_title",
    "traveler_xp",
    "traveler_title",
    "strength_title",
    # new face sensors (if present)
    "face",
    "mood",
]

_META: Dict[str, Dict[str, Any]] = {
    "last_seen":      {"icon": "mdi:clock-check", "device_class": SensorDeviceClass.TIMESTAMP},
    "handshakes":     {"icon": "mdi:handshake"},
    "points":         {"icon": "mdi:star"},
    "epochs":         {"icon": "mdi:progress-clock"},
    "train_epochs":   {"icon": "mdi:arm-flex"},
    "cpu_temp":       {"icon": "mdi:thermometer", "device_class": SensorDeviceClass.TEMPERATURE, "unit": UnitOfTemperature.CELSIUS},
    "age_index":      {"icon": "mdi:crown-outline"},
    "age_title":      {"icon": "mdi:crown"},
    "traveler_xp":    {"icon": "mdi:map-marker-distance"},
    "traveler_title": {"icon": "mdi:suitcase"},
    "strength_title": {"icon": "mdi:lightning-bolt"},
    "face":           {"icon": "mdi:emoticon-outline"},
    "mood":           {"icon": "mdi:emoticon"},
}

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities) -> None:
    data = hass.data[DOMAIN][entry.entry_id]
    address: str = data.get("address") or entry.unique_id or "pwnagotchi"
    entities: list[Entity] = [PwnagotchiSensor(address, key) for key in _KEYS]
    async_add_entities(entities)

class PwnagotchiSensor(SensorEntity):
    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, address: str, key: str) -> None:
        self._address = address
        self._key = key
        base = address or "pwnagotchi"
        self._attr_unique_id = f"{base}|{key}"
        self._attr_name = f"Pwnagotchi {self._nice(key)}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, base)},
            connections={(CONNECTION_BLUETOOTH, base)},
            manufacturer="Pwnagotchi",
            model="BLE Beacon",
            name="Pwnagotchi",
        )

        meta = _META.get(key, {})
        if "icon" in meta:
            self._attr_icon = meta["icon"]
        if "device_class" in meta:
            self._attr_device_class = meta["device_class"]
        if "unit" in meta:
            self._attr_native_unit_of_measurement = meta["unit"]

    def _nice(self, key: str) -> str:
        nm = key.replace("_", " ").title()
        nm = nm.replace("Cpu Temp", "CPU Temp")
        return nm

    @property
    def available(self) -> bool:
        return self._address in LAST_VALUES

    @property
    def native_value(self) -> Any:
        return LAST_VALUES.get(self._address, {}).get(self._key)

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(async_dispatcher_connect(self.hass, _sig(self._address), self._handle_update))

    @callback
    def _handle_update(self) -> None:
        self.async_write_ha_state()
