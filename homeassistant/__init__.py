from __future__ import annotations

import logging
import struct

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform, UnitOfTemperature, PERCENTAGE
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from homeassistant.components.bluetooth import (
    BluetoothScanningMode,
    BluetoothServiceInfoBleak,
)
from homeassistant.components.bluetooth.passive_update_processor import (
    PassiveBluetoothDataUpdate,
    PassiveBluetoothEntityKey,
    PassiveBluetoothProcessorCoordinator,
)
from homeassistant.helpers.device_registry import DeviceInfo, CONNECTION_BLUETOOTH
from homeassistant.components.sensor import SensorDeviceClass, SensorEntityDescription, SensorStateClass

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.BINARY_SENSOR]

# Entity keys
K_RSSI = PassiveBluetoothEntityKey(key="rssi", device_id=None)
K_SEEN = PassiveBluetoothEntityKey(key="last_seen", device_id=None)
K_PAYL = PassiveBluetoothEntityKey(key="payload_hex", device_id=None)

K_HAND = PassiveBluetoothEntityKey(key="handshakes", device_id=None)
K_POINTS = PassiveBluetoothEntityKey(key="points", device_id=None)
K_EPOCHS = PassiveBluetoothEntityKey(key="epochs", device_id=None)
K_TRAIN = PassiveBluetoothEntityKey(key="train_epochs", device_id=None)
K_TEMP = PassiveBluetoothEntityKey(key="cpu_temp_c", device_id=None)
K_BATT = PassiveBluetoothEntityKey(key="battery_pct", device_id=None)
K_CHRG = PassiveBluetoothEntityKey(key="charging", device_id=None)  # binary_sensor
K_AGE = PassiveBluetoothEntityKey(key="age_index", device_id=None)
K_STR = PassiveBluetoothEntityKey(key="strength_index", device_id=None)

# Derived titles
K_AGE_TITLE = PassiveBluetoothEntityKey(key="age_title", device_id=None)
K_TRAV_TITLE = PassiveBluetoothEntityKey(key="traveler_title", device_id=None)
K_STR_TITLE = PassiveBluetoothEntityKey(key="strength_title", device_id=None)

# Optional numeric XP (hidden by default)
K_TRAV_XP = PassiveBluetoothEntityKey(key="traveler_xp", device_id=None)

DESC_RSSI = SensorEntityDescription(
    key="rssi",
    name="Pwnagotchi RSSI",
    native_unit_of_measurement="dBm",
    device_class=SensorDeviceClass.SIGNAL_STRENGTH,
    state_class=SensorStateClass.MEASUREMENT,
    entity_registry_enabled_default=False,
)
DESC_SEEN = SensorEntityDescription(
    key="last_seen",
    name="Pwnagotchi Last Seen",
    device_class=SensorDeviceClass.TIMESTAMP,
    entity_registry_enabled_default=True,
)
DESC_PAYL = SensorEntityDescription(
    key="payload_hex",
    name="Pwnagotchi Payload (hex)",
    icon="mdi:code-tags",
    entity_registry_enabled_default=False,
)

DESC_HAND = SensorEntityDescription(
    key="handshakes",
    name="Pwnagotchi Handshakes",
    icon="mdi:handshake",
    state_class=SensorStateClass.TOTAL_INCREASING,
)
DESC_POINTS = SensorEntityDescription(
    key="points",
    name="Pwnagotchi Points",
    icon="mdi:star-four-points",
    state_class=SensorStateClass.MEASUREMENT,
)
DESC_EPOCHS = SensorEntityDescription(
    key="epochs",
    name="Pwnagotchi Epochs",
    icon="mdi:counter",
    state_class=SensorStateClass.MEASUREMENT,
)
DESC_TRAIN = SensorEntityDescription(
    key="train_epochs",
    name="Pwnagotchi Train Epochs",
    icon="mdi:arm-flex",
    state_class=SensorStateClass.MEASUREMENT,
    entity_registry_enabled_default=False,
)
DESC_TEMP = SensorEntityDescription(
    key="cpu_temp_c",
    name="Pwnagotchi CPU Temp",
    device_class=SensorDeviceClass.TEMPERATURE,
    native_unit_of_measurement=UnitOfTemperature.CELSIUS,
    state_class=SensorStateClass.MEASUREMENT,
)
DESC_BATT = SensorEntityDescription(
    key="battery_pct",
    name="Pwnagotchi Battery",
    device_class=SensorDeviceClass.BATTERY,
    native_unit_of_measurement=PERCENTAGE,
    state_class=SensorStateClass.MEASUREMENT,
)
DESC_AGE = SensorEntityDescription(
    key="age_index",
    name="Pwnagotchi Age Index",
    icon="mdi:cake-variant-outline",
    state_class=SensorStateClass.MEASUREMENT,
    entity_registry_enabled_default=False,
)
DESC_STR = SensorEntityDescription(
    key="strength_index",
    name="Pwnagotchi Strength Index",
    icon="mdi:arm-flex",
    state_class=SensorStateClass.MEASUREMENT,
    entity_registry_enabled_default=False,
)
DESC_AGE_TITLE = SensorEntityDescription(
    key="age_title",
    name="Pwnagotchi Age Title",
    icon="mdi:crown-outline",
    entity_registry_enabled_default=True,
)
DESC_TRAV_TITLE = SensorEntityDescription(
    key="traveler_title",
    name="Pwnagotchi Traveler Title",
    icon="mdi:bag-suitcase-outline",
    entity_registry_enabled_default=True,
)
DESC_STR_TITLE = SensorEntityDescription(
    key="strength_title",
    name="Pwnagotchi Strength Title",
    icon="mdi:sword-cross",
    entity_registry_enabled_default=True,
)
DESC_TRAV_XP = SensorEntityDescription(
    key="traveler_xp",
    name="Pwnagotchi Traveler XP",
    icon="mdi:map-marker-distance",
    state_class=SensorStateClass.MEASUREMENT,
    entity_registry_enabled_default=False,
)

# Title thresholds (match your plugins exactly)
AGE_TITLES = {
    100:     "Cosmic Hatchling",
    200:     "Pingling",
    275:     "Bootsprout",
    350:     "Fledgling",
    450:     "Bitling",
    600:     "Beacon Scout",
    750:     "Orbitling",
    900:     "Neural Youngling",
    1050:    "Qubitling",
    1200:    "Cipher Cadet",
    1350:    "Beacon Squire",
    1500:    "Packeteer",
    2000:    "Signalist",
    3000:    "Hex Horizonist",
    4000:    "Hash Hunter",
    5000:    "Nebulist",
    7000:    "Kernel Keeper",
    10000:   "Encrypted Sage",
    15000:   "Grandmaster",
    20000:   "Celestial Ancestor",
    30000:   "Ethernaut",
    40000:   "Binary Venerable",
    55000:   "Quantum Overlord",
    80000:   "Primordial",
    100000:  "Galactic Root",
    111111:  "Singularity Sentinel",
}

TRAVELER_TITLES = {
    0: "Homebody",
    200: "Wanderling",
    600: "City Stroller",
    1200: "Road Warrior",
    2400: "Jetsetter",
    4800: "Globetrotter",
}

STRENGTH_TITLES = {
    100: "Circuit Initiate",
    250: "Pulse Drifter",
    400: "Bitbreaker",
    600: "Packet Slinger",
    900: "Firewall Skipper",
    1200: "Deauth Cadet",
    1600: "Hash Harvester",
    2000: "Spectral Scrambler",
    2500: "Protocol Predator",
    3200: "Cipher Crusher",
    4500: "WiFi Marauder",
    6000: "Neural Nullifier",
    8000: "Signal Saboteur",
    12000: "Astral Sniffer",
    18000: "Quantum Brawler",
    30000: "Rootwave Ronin",
    55555: "Void Breaker",
    111111: "Omega Cipherlord",
}

def _title_from_value(val: int | None, table: dict[int, str]) -> str:
    if not isinstance(val, int):
        return "Unknown"
    title = "Unknown"
    for threshold in sorted(table.keys()):
        if val >= threshold:
            title = table[threshold]
        else:
            break
    return title


def _parse_payload(payload: bytes) -> dict:
    out: dict[str, object] = {}
    if not payload or len(payload) < 12:
        return out
    try:
        ver = payload[0]
        if ver >= 3 and len(payload) >= 17:
            # v3: B H H H B B B B B B H H
            #  -> ver, hs, pts, ep, tx2, batt, flags, age_idx, str_idx, reserved, trav_xp, train_epochs
            ver, hs, pts, ep, tx2, batt, flags, age, strength, _res = struct.unpack('<BHHHBBBBBB', payload[:13])
            trav_xp = int.from_bytes(payload[13:15], 'little', signed=False)
            train_ep = int.from_bytes(payload[15:17], 'little', signed=False)
            out.update({
                'traveler_xp': trav_xp,
                'train_epochs': train_ep,
            })
        else:
            # v1/v2: B H H H B B B B B [B]
            ver, hs, pts, ep, tx2, batt, flags, age, strength = struct.unpack('<BHHHBBBBB', payload[:12])

        out.update({
            'handshakes': int(hs),
            'points': int(pts),
            'epochs': int(ep),
            'cpu_temp_c': round(float(tx2) / 2.0, 1),
            'battery_pct': None if batt == 255 else int(batt),
            'charging': bool(flags & 0x01),
            'age_index': int(age),
            'strength_index': int(strength),
        })
    except Exception:
        pass
    return out


def _update_from_adv(service_info: BluetoothServiceInfoBleak) -> PassiveBluetoothDataUpdate:
    mac = service_info.address
    name = service_info.name or 'Pwnagotchi'
    payload = service_info.manufacturer_data.get(0xFFFF, b'')
    values = _parse_payload(payload)

    dev = DeviceInfo(
        name=f"{name} (BLE)",
        connections={(CONNECTION_BLUETOOTH, mac)},
        manufacturer="Pwnagotchi",
        model="BLE Beacon",
    )

    descriptions = {
        K_RSSI: DESC_RSSI,
        K_SEEN: DESC_SEEN,
        K_PAYL: DESC_PAYL,
        K_HAND: DESC_HAND,
        K_POINTS: DESC_POINTS,
        K_EPOCHS: DESC_EPOCHS,
        K_TRAIN: DESC_TRAIN,
        K_TEMP: DESC_TEMP,
        K_BATT: DESC_BATT,
        K_AGE: DESC_AGE,
        K_STR: DESC_STR,
        K_AGE_TITLE: DESC_AGE_TITLE,
        K_TRAV_TITLE: DESC_TRAV_TITLE,
        K_STR_TITLE: DESC_STR_TITLE,
        K_TRAV_XP: DESC_TRAV_XP,
    }

    data = {
        K_RSSI: service_info.rssi,
        K_SEEN: dt_util.utcnow(),
        K_PAYL: payload.hex(),
    }
    for key, k in (
        ('handshakes', K_HAND),
        ('points', K_POINTS),
        ('epochs', K_EPOCHS),
        ('train_epochs', K_TRAIN),
        ('cpu_temp_c', K_TEMP),
        ('battery_pct', K_BATT),
        ('age_index', K_AGE),
        ('strength_index', K_STR),
        ('charging', K_CHRG),   # used by binary_sensor processor
        ('traveler_xp', K_TRAV_XP),
    ):
        if key in values:
            data[k] = values[key]

    # Derived Titles
    age_title = _title_from_value(values.get('epochs'), AGE_TITLES)
    trav_title = _title_from_value(values.get('traveler_xp'), TRAVELER_TITLES)
    str_title = _title_from_value(values.get('train_epochs'), STRENGTH_TITLES)
    data[K_AGE_TITLE] = age_title
    data[K_TRAV_TITLE] = trav_title
    data[K_STR_TITLE] = str_title

    names = {
        K_RSSI: 'Pwnagotchi RSSI',
        K_SEEN: 'Pwnagotchi Last Seen',
        K_PAYL: 'Pwnagotchi Payload (hex)',
        K_HAND: 'Pwnagotchi Handshakes',
        K_POINTS: 'Pwnagotchi Points',
        K_EPOCHS: 'Pwnagotchi Epochs',
        K_TRAIN: 'Pwnagotchi Train Epochs',
        K_TEMP: 'Pwnagotchi CPU Temp',
        K_BATT: 'Pwnagotchi Battery',
        K_AGE: 'Pwnagotchi Age Index',
        K_STR: 'Pwnagotchi Strength Index',
        K_CHRG: 'Pwnagotchi Charging',
        K_TRAV_XP: 'Pwnagotchi Traveler XP',
        K_AGE_TITLE: 'Pwnagotchi Age Title',
        K_TRAV_TITLE: 'Pwnagotchi Traveler Title',
        K_STR_TITLE: 'Pwnagotchi Strength Title',
    }

    return PassiveBluetoothDataUpdate(
        devices={None: dev},
        entity_descriptions=descriptions,
        entity_data=data,
        entity_names=names,
    )


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    address = entry.unique_id
    coordinator = hass.data.setdefault(DOMAIN, {})[entry.entry_id] = PassiveBluetoothProcessorCoordinator(
        hass,
        _LOGGER,
        address=address,
        mode=BluetoothScanningMode.PASSIVE,
        connectable=False,
        update_method=_update_from_adv,
    )
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(coordinator.async_start())
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unload_ok
