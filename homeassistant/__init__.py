\
from __future__ import annotations
from typing import Any, Dict
import logging
from datetime import datetime, timezone

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo, CONNECTION_BLUETOOTH
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.components.bluetooth import (
    BluetoothScanningMode,
    BluetoothServiceInfoBleak,
)
from homeassistant.components.bluetooth.passive_update_processor import (
    PassiveBluetoothDataUpdate,
    PassiveBluetoothProcessorCoordinator,
)

from .const import (
    DOMAIN, MANUFACTURER_ID,
    age_index_from_epochs, age_title_from_epochs,
    strength_title_from_train, traveler_title_from_xp,
    FACE_ID_TO_FACE, FACE_ID_TO_MOOD,
)

_LOGGER = logging.getLogger(__name__)
PLATFORMS: list[Platform] = [Platform.SENSOR]
LAST_VALUES: Dict[str, Dict[str, Any]] = {}

def _sig(address: str) -> str:
    return f"{DOMAIN}_adv_{address}"

def _mk_update(*, address: str, device_info: DeviceInfo | None = None) -> PassiveBluetoothDataUpdate:
    devices: Dict[str, DeviceInfo] = {}
    if device_info:
        devices[address] = device_info
    return PassiveBluetoothDataUpdate(devices=devices, entity_descriptions={}, entity_data={}, entity_names={})

def _parse_payload(mfr: bytes) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    if not mfr or len(mfr) < 2:
        return out
    ver = mfr[0]
    body = mfr[1:]
    try:
        # v6: +face_id (1B) +face_rev (1B)
        if ver >= 6 and len(body) >= 13:
            hs  = int.from_bytes(body[0:2],  'little')
            pts = int.from_bytes(body[2:4],  'little')
            ep  = int.from_bytes(body[4:6],  'little')
            cpu = body[6] / 2.0
            trav= int.from_bytes(body[7:9],  'little')
            tr  = int.from_bytes(body[9:11], 'little')
            face_id = body[11]
            # face_rev = body[12]  # currently unused, reserved for migrations
            out.update({
                "handshakes": hs,
                "points": pts,
                "epochs": ep,
                "cpu_temp": cpu,
                "traveler_xp": trav,
                "train_epochs": tr,
            })
            out["age_index"] = age_index_from_epochs(ep)
            out["age_title"] = age_title_from_epochs(ep)
            out["strength_title"] = strength_title_from_train(tr)
            out["traveler_title"] = traveler_title_from_xp(trav)
            if face_id:
                out["face"] = FACE_ID_TO_FACE.get(face_id, "unknown")
                out["mood"] = FACE_ID_TO_MOOD.get(face_id, "unknown")
            return out

        # v5 compact (no face)
        if ver >= 5 and len(body) >= 11:
            hs  = int.from_bytes(body[0:2],  'little')
            pts = int.from_bytes(body[2:4],  'little')
            ep  = int.from_bytes(body[4:6],  'little')
            cpu = body[6] / 2.0
            trav= int.from_bytes(body[7:9],  'little')
            tr  = int.from_bytes(body[9:11], 'little')
            out.update({
                "handshakes": hs,
                "points": pts,
                "epochs": ep,
                "cpu_temp": cpu,
                "traveler_xp": trav,
                "train_epochs": tr,
            })
            out["age_index"] = age_index_from_epochs(ep)
            out["age_title"] = age_title_from_epochs(ep)
            out["strength_title"] = strength_title_from_train(tr)
            out["traveler_title"] = traveler_title_from_xp(trav)
            return out

        # v3 legacy (we ignore built-in indexes)
        if ver >= 3 and len(body) >= 15:
            hs  = int.from_bytes(body[0:2],  'little')
            pts = int.from_bytes(body[2:4],  'little')
            ep  = int.from_bytes(body[4:6],  'little')
            cpu = body[6] / 2.0
            trav = int.from_bytes(body[11:13], 'little') if len(body) >= 13 else 0
            tr   = int.from_bytes(body[13:15], 'little') if len(body) >= 15 else 0
            out.update({
                "handshakes": hs,
                "points": pts,
                "epochs": ep,
                "cpu_temp": cpu,
                "traveler_xp": trav,
                "train_epochs": tr,
            })
            out["age_index"] = age_index_from_epochs(ep)
            out["age_title"] = age_title_from_epochs(ep)
            out["strength_title"] = strength_title_from_train(tr)
            out["traveler_title"] = traveler_title_from_xp(trav)
    except Exception as e:
        _LOGGER.debug("Failed to parse payload: %s", e)
    return out

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    address_hint: str = entry.data.get("address") or (entry.unique_id or "")

    def _update_from_adv(service_info: BluetoothServiceInfoBleak) -> PassiveBluetoothDataUpdate:
        address = service_info.address or address_hint or "pwnagotchi"
        name = service_info.name or "Pwnagotchi"
        mfr = (service_info.manufacturer_data or {}).get(MANUFACTURER_ID)
        if not mfr:
            return PassiveBluetoothDataUpdate(devices={}, entity_descriptions={}, entity_data={}, entity_names={})

        device = DeviceInfo(
            identifiers={(DOMAIN, address)},
            connections={(CONNECTION_BLUETOOTH, address)},
            name=name,
            manufacturer="Pwnagotchi",
            model="BLE Beacon",
        )

        now_dt = datetime.now(timezone.utc)
        bucket = LAST_VALUES.setdefault(address, {})
        bucket["rssi"] = service_info.rssi
        bucket["last_seen"] = now_dt
        bucket["payload_hex"] = mfr.hex()

        stats = _parse_payload(bytes(mfr))
        bucket.update(stats)

        async_dispatcher_send(hass, _sig(address))
        return _mk_update(address=address, device_info=device)

    coordinator = PassiveBluetoothProcessorCoordinator(
        hass,
        _LOGGER,
        address=address_hint,
        mode=BluetoothScanningMode.PASSIVE,
        connectable=False,
        update_method=_update_from_adv,
    )

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "coordinator": coordinator,
        "address": address_hint,
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(coordinator.async_start())
    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
    return unload_ok
