import os, json, time, threading, struct, subprocess, logging

import pwnagotchi
import pwnagotchi.plugins as plugins

LOGGER = logging.getLogger("plg.ble_beacon")

DEFAULTS = {
    "interval_s": 20,
    "age_json": "/root/age_strength.json",
    "traveler_json": "/root/pwn_traveler.json",
    "company_id": 0xFFFF,
    "hci": "hci0",
    "broadcast_face": True,   # toggle face in BLE v6
}

# Keep in sync with Home Assistant const.py
FACE_TABLE = {
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
FACE_STR_TO_ID = {v: k for k, v in FACE_TABLE.items()}
FACE_REV = 1

class BLEBeacon(plugins.Plugin):
    __author__ = "MediaCutlet/Strato"
    __version__ = "0.7.0"
    __license__ = "MIT"
    __description__ = "Broadcast Pwnagotchi stats over BLE manufacturer data (v5 compact, optional v6 face)."

    def __init__(self):
        self.opts = dict(DEFAULTS)
        self._stop = threading.Event()
        self._thread = None
        self._face_id = 0

    def on_loaded(self):
        try:
            for k, v in (self.options or {}).items():
                self.opts[k] = v
        except Exception:
            pass
        self._thread = threading.Thread(target=self._loop, name="ble_beacon", daemon=True)
        self._thread.start()

    # capture face changes via UI updates
    def on_ui_update(self, ui):
        try:
            face = None
            if hasattr(ui, "get"):
                face = ui.get("face")
            # unsafe but common in plugins: try to access state dict
            if not face and hasattr(ui, "_state"):
                face = ui._state.get("face")
            if isinstance(face, str):
                self._face_id = FACE_STR_TO_ID.get(face, 0)
        except Exception:
            pass

    def on_unloaded(self):
        self._stop.set()
        try:
            if self._thread:
                self._thread.join(timeout=2)
        except Exception:
            pass
        try:
            self._run(["/usr/bin/hcitool","-i",self.opts["hci"],"cmd","0x08","0x000a","00"])
        except Exception:
            pass

    def _run(self, cmd, timeout=3):
        try:
            p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout, check=False)
            return p.returncode == 0
        except Exception:
            return False

    def _read_age_json(self):
        d = {}
        p = self.opts["age_json"]
        try:
            if os.path.exists(p):
                with open(p, "r") as f:
                    d = json.load(f)
        except Exception:
            pass
        hs = int(d.get("handshakes", 0))
        pts = int(d.get("points", 0))
        ep = int(d.get("epochs", 0))
        tr = int(d.get("train_epochs", d.get("trainings", 0)))
        return hs, pts, ep, tr

    def _read_traveler_json(self):
        p = self.opts.get("traveler_json", "/root/pwn_traveler.json")
        xp = 0
        try:
            if os.path.exists(p):
                with open(p, "r") as f:
                    d = json.load(f)
                xp = int(d.get("travel_xp", 0))
        except Exception:
            pass
        return xp

    def _read_cpu_temp(self):
        try:
            with open("/sys/class/thermal/thermal_zone0/temp", "r") as f:
                milli = int(f.read().strip())
            c = max(0.0, min(127.5, milli / 1000.0))
            return int(round(c * 2.0))
        except Exception:
            return 0

    def _build_payload_v5(self):
        hs, pts, ep, tr = self._read_age_json()
        tx2 = self._read_cpu_temp()
        trav_xp = self._read_traveler_json()

        hs = max(0, min(65535, hs))
        pts = max(0, min(65535, pts))
        ep = max(0, min(65535, ep))
        trav_xp = max(0, min(65535, trav_xp))
        tr = max(0, min(65535, tr))
        tx2 = max(0, min(255, tx2))

        return struct.pack("<BHHHBHH", 5, hs, pts, ep, tx2, trav_xp, tr)

    def _build_payload_v6(self):
        hs, pts, ep, tr = self._read_age_json()
        tx2 = self._read_cpu_temp()
        trav_xp = self._read_traveler_json()

        hs = max(0, min(65535, hs))
        pts = max(0, min(65535, pts))
        ep = max(0, min(65535, ep))
        trav_xp = max(0, min(65535, trav_xp))
        tr = max(0, min(65535, tr))
        tx2 = max(0, min(255, tx2))

        face_id = int(self._face_id) & 0xFF
        face_rev = int(FACE_REV) & 0xFF

        # <BHHHBHHBB> = ver(6), hs, pts, ep, cpu*2, trav_xp, train_ep, face_id, face_rev
        return struct.pack("<BHHHBHHBB", 6, hs, pts, ep, tx2, trav_xp, tr, face_id, face_rev)

    def _ble_set_adv(self, payload: bytes):
        hci = self.opts["hci"]
        cid = int(self.opts["company_id"]) & 0xFFFF
        flags = bytes([2, 0x01, 0x06])
        mfg = bytes([len(payload) + 3, 0xFF, cid & 0xFF, (cid >> 8) & 0xFF]) + payload
        adv = flags + mfg
        if len(adv) > 31:
            adv = adv[:31]
        pad = bytes([0x00] * (31 - len(adv)))
        data = bytes([len(adv)]) + adv + pad

        self._run(["/usr/bin/hcitool","-i",hci,"cmd","0x08","0x000a","00"])
        self._run(["/usr/bin/hciconfig", hci, "leadv", "0"])
        self._run(["/usr/bin/hciconfig", hci, "up"])
        hexbytes = [f"{b:02x}" for b in data]
        self._run(["/usr/bin/hcitool","-i",hci,"cmd","0x08","0x0008", *hexbytes[:31]])
        self._run(["/usr/bin/hcitool","-i",hci,"cmd","0x08","0x000a","01"])
        self._run(["/usr/bin/hciconfig", hci, "leadv", "3"])

    def _loop(self):
        interval = int(self.opts.get("interval_s", 20))
        use_face = bool(self.opts.get("broadcast_face", True))
        while not self._stop.is_set():
            try:
                payload = self._build_payload_v6() if use_face else self._build_payload_v5()
                self._ble_set_adv(payload)
            except Exception:
                pass
            self._stop.wait(interval)
