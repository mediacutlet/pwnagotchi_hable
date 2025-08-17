\
from __future__ import annotations
from typing import Dict, List, Tuple

DOMAIN = "pwnagotchi_ble"
MANUFACTURER_ID = 0xFFFF

# === Title tables (as in your plugins) ===

DEFAULT_AGE_TITLES: Dict[int, str] = {
  100:     "Hatchling",
  200:     "Pingling",
  300:     "Bootsprout",
  500:     "Fledgling",
  700:     "Bitling",
  1_000:   "Orbitling",
  1_500:   "Qubitling",
  2_500:   "Pingpunk",
  3_000:   "Telemetry Tween",
  3_500:   "Cipher Teen",
  4_250:   "Beacon Teen",
  5_000:   "Protocol Teen",
  6_000:   "Emergent Adult",
  7_000:   "Young Adult",
  8_000:   "Mature",
  9_000:   "Seasoned",
  10_000:  "Elder",
  12_000:  "Encrypted Sage",
  15_000:  "Ancient",
  20_000:  "Celestial Ancestor",
  30_000:  "Eon Ancestor",
  40_000:  "Binary Venerable",
  62_000:  "Quantum Elder",
  75_000:  "Primordial",
  100_000: "Galactic Root",
  111_111: "Singularity"
}

DEFAULT_STRENGTH_TITLES: Dict[int, str] = {
    100: "Neophyte",
    250: "Cyber Trainee",
    400: "Bitbreaker",
    600: "Packet Slinger",
    900: "Kernel Keeper",
    1_200: "Deauth Cadet",
    1_600: "Packeteer",
    2_000: "Hash Hunter",
    2_500: "Signalist",
    3_200: "Ethernaut",
    4_500: "WiFi Marauder",
    6_000: "Neural Saboteur",
    8_000: "Astral Admiral",
    12_000: "Signal Master",
    18_000: "Quantum Brawler",
    30_000: "Rootwave Titan",
    55_555: "Void Breaker",
    111_111: "Omega Cipherlord"
}

TRAVEL_TITLES: Dict[int, str] = {
    0: "Homebody",
    200: "Wanderling",
    600: "City Stroller",
    1200: "Road Warrior",
    2400: "Jetsetter",
    4800: "Globetrotter",
}

# === Face table ===
# We assign stable numeric IDs to the canonical faces.
# 0 == unknown/not-broadcast. Keep this in sync with the plugin if you add/remove faces.
FACE_REV = 1  # bump if the mapping changes
FACE_ID_TO_FACE: Dict[int, str] = {
    1: "(⇀‿‿↼)",   # sleeping
    2: "(≖‿‿≖)",   # awakening
    3: "(◕‿‿◕)",   # awake / normal
    4: "( ⚆⚆)",    # observing (neutral)
    5: "(☉☉ )",    # observing (neutral) alt
    6: "( ◕‿◕)",   # observing (happy)
    7: "(◕‿◕ )",   # observing (happy) alt
    8: "(°▃▃°)",   # intense
    9: "(⌐■_■)",   # cool
    10: "(•‿‿•)",  # happy
    11: "(^‿‿^)",  # grateful
    12: "(ᵔ◡◡ᵔ)", # excited
    13: "(✜‿‿✜)", # smart
    14: "(♥‿‿♥)", # friendly
    15: "(☼‿‿☼)", # motivated
    16: "(≖__≖)", # demotivated
    17: "(-__-)",  # bored
    18: "(╥☁╥ )", # sad
    19: "(ب__ب)",  # lonely
    20: "(☓‿‿☓)", # broken
    21: "(#__#)",  # debugging
}

# Mood labels for automations (group similar faces together)
FACE_ID_TO_MOOD: Dict[int, str] = {
    1: "sleeping",
    2: "awakening",
    3: "normal",
    4: "observing_neutral",
    5: "observing_neutral",
    6: "observing_happy",
    7: "observing_happy",
    8: "intense",
    9: "cool",
    10: "happy",
    11: "grateful",
    12: "excited",
    13: "smart",
    14: "friendly",
    15: "motivated",
    16: "demotivated",
    17: "bored",
    18: "sad",
    19: "lonely",
    20: "broken",
    21: "debugging",
}

# Reverse lookup helper
FACE_STR_TO_ID: Dict[str, int] = {v: k for k, v in FACE_ID_TO_FACE.items()}

def _sorted_thresholds(d: Dict[int, str]) -> List[Tuple[int, str]]:
    return sorted(d.items(), key=lambda kv: kv[0])

def title_for_value(value: int, table: Dict[int, str]) -> str:
    last = next(iter(table.values()))
    for thr, name in _sorted_thresholds(table):
        if value >= thr:
            last = name
        else:
            break
    return last

def index_for_value(value: int, table: Dict[int, str]) -> int:
    idx = 0
    for thr, _ in _sorted_thresholds(table):
        if value >= thr:
            idx += 1
        else:
            break
    return idx

def age_index_from_epochs(epochs: int) -> int:
    return index_for_value(int(epochs), DEFAULT_AGE_TITLES)

def age_title_from_epochs(epochs: int) -> str:
    return title_for_value(int(epochs), DEFAULT_AGE_TITLES)

def strength_title_from_train(train_epochs: int) -> str:
    return title_for_value(int(train_epochs), DEFAULT_STRENGTH_TITLES)

def traveler_title_from_xp(xp: int) -> str:
    return title_for_value(int(xp), TRAVEL_TITLES)
