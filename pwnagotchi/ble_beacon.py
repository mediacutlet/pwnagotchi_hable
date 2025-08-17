import os, json, time, threading, struct, subprocess, logging
import pwnagotchi
import pwnagotchi.plugins as plugins

LOGGER = logging.getLogger("plg.ble_beacon")

FACE_CODES = {
    "cool":1,"sleep":2,"angry":3,"sad":4,"friend":5,"smile":6,"excited":7,
    "look_r":8,"look_l":9,"intense":10,"smart":11,"bored":12,"happy":13,
    "grin":14,"monocle":15,"quiet":16,"shy":17,"evil":18,"awake":19,"debug":20
}

_DIAG = "/tmp/ble_beacon.diag"

def _mark(msg: str):
    try:
        with open(_DIAG, "a") as f:
            f.write(time.strftime('%H:%M:%S ') + str(msg) + "\n")
    except Exception:
        pass

DEFAULTS = {
    # BLE cadence (20s recommended after testing)
    "interval_s": 20,
    # Age plugin persistence (epochs, train_epochs, points, handshakes, etc.)
    "age_json": "/root/age_strength.json",
    # Nomadachi persistence (traveler_xp lives here)
    "traveler_json": "/root/pwn_traveler.json",
    # BLE manufacturer company ID (0xFFFF internal use is fine)
    "company_id": 0xFFFF,
    # HCI name
    "hci": "hci0",
    # battery readouts (optional PiSugar REST)
    "enable_battery": True,
    "pisugar_url": "http://127.0.0.1:8421/status",
}

# Advert layout v3 (little-endian)
# B  ver          (always 3 for this layout)
# H  handshakes
# H  points
# H  epochs
# B  cpu_temp_x2  (C * 2)
# B  battery_pct  (0..100, 255=unknown)
# B  flags        (bit0 = charging)
# B  age_index    (kept for legacy charts; not used for title now)
# B  strength_idx (kept for legacy charts)
# B  reserved     (0)
# H  traveler_xp
# H  train_epochs

class BLEBeacon(plugins.Plugin):
    __author__ = "MediaCutlet/Strato"
    __version__ = "0.3.0"
    __license__ = "MIT"
    __description__ = "Broadcast Pwnagotchi stats over BLE manufacturer data (v3)."

    def __init__(self):
        self.opts = dict(DEFAULTS)
        self._stop = threading.Event()
        self._thread = None

    # ---- lifecycle ----
    def on_loaded(self):
        self._last_face = 'Unknown'
        # merge config
        try:
            for k, v in (self.options or {}).items():
                self.opts[k] = v
        except Exception:
            pass
        _mark("on_loaded")
        # background loop
        self._thread = threading.Thread(target=self._loop, name="ble_beacon", daemon=True)
        self._thread.start()

    def on_unloaded(self):
        self._stop.set()
        try:
            if self._thread:
                self._thread.join(timeout=2)
        except Exception:
            pass
        # best effort: disable adv
        try:
            self._run(["/usr/bin/hcitool","-i",self.opts["hci"],"cmd","0x08","0x000a","00"])
        except Exception:
            pass

    # ---- helpers ----
    def _run(self, cmd, timeout=3):
        try:
            p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout, check=False)
            _mark(f"run: {' '.join(cmd)} rc={p.returncode} err={p.stderr.decode(errors='ignore').strip()}")
            return p.returncode == 0 + bytes([face_code])
        except Exception as e:
            _mark(f"run error: {e}")
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
        # Normalize ints
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
        # /sys/class/thermal/thermal_zone0/temp -> millidegC
        try:
            with open("/sys/class/thermal/thermal_zone0/temp", "r") as f:
                milli = int(f.read().strip())
            c = max(0.0, min(127.5, milli / 1000.0))
            return int(round(c * 2.0))
        except Exception:
            return 0

    def _read_battery(self):
        if not self.opts.get("enable_battery", True):
            return 255, False
        # PiSugar REST if present
        try:
            import urllib.request, json as _json
            with urllib.request.urlopen(self.opts["pisugar_url"], timeout=0.5) as r:
                j = _json.loads(r.read().decode("utf-8"))
            pct = int(round(float(j.get("battery", {}).get("percentage", 0))))
            charging = bool(j.get("battery", {}).get("is_charging", False))
            pct = max(0, min(100, pct))
            return pct, charging
        except Exception:
            return 255, False

    def _age_index_from_epochs(self, epochs: int) -> int:
        # lightweight, just bucketize so legacy graphs have a rough index
        # (title now computed in HA from epochs directly)
        if epochs <= 0: return 0
        if epochs >= 111111: return 20
        # coarse ~ 20 buckets
        return max(1, min(20, epochs // 600))

    def _strength_index_from_train(self, tr: int) -> int:
        if tr <= 0: return 0
        if tr >= 111111: return 20
        return max(1, min(20, tr // 300))

    def _build_payload(self) -> bytes:
        hs, pts, ep, tr = self._read_age_json()
        tx2 = self._read_cpu_temp()
        batt, charging = self._read_battery()
        trav_xp = self._read_traveler_json()

        flags = 0x01 if charging else 0x00
        age_idx = self._age_index_from_epochs(ep)
        str_idx = self._strength_index_from_train(tr)

        # clamp
        hs = max(0, min(65535, hs))
        pts = max(0, min(65535, pts))
        ep = max(0, min(65535, ep))
        trav_xp = max(0, min(65535, trav_xp))
        tr = max(0, min(65535, tr))
        tx2 = max(0, min(255, tx2))
        batt = 255 if batt is None else max(0, min(255, batt))
        age_idx = max(0, min(255, age_idx))
        str_idx = max(0, min(255, str_idx))

        head = struct.pack("<BHHHBBBBBB", 3, hs, pts, ep, tx2, batt, flags, age_idx, str_idx, 0)
        tail = struct.pack("<HH", trav_xp, tr)
        return head + tail  # 17 bytes

    def _ble_set_adv(self, payload: bytes):
        """Disable -> set params -> set data -> enable (avoids 0x0c)."""
        hci = self.opts["hci"]
        cid = int(self.opts["company_id"]) & 0xFFFF

        # Build AD: Flags + Manufacturer data
        flags = bytes([2, 0x01, 0x06])
        mfg = bytes([len(payload) + 3, 0xFF, cid & 0xFF, (cid >> 8) & 0xFF]) + payload
        adv = flags + mfg
        # pad to 31
        if len(adv) > 31:
            adv = adv[:31]
        pad = bytes([0x00] * (31 - len(adv)))
        data = bytes([len(adv)]) + adv + pad  # length + data + zeros

        # Stop, set params, set data, start
        self._run(["/usr/bin/hcitool","-i",hci,"cmd","0x08","0x000a","00"])
        self._run(["/usr/bin/hciconfig", hci, "leadv", "0"])
        self._run(["/usr/bin/hciconfig", hci, "up"])
        # params: 0x0006 (min=max=100ms, ADV_IND, public, ch 37-39, all allowed)
        # 0x0006 removed – use BlueZ defaults
# data: 0x0008
        hexbytes = [f"{b:02x}" for b in data]
        self._run(["/usr/bin/hcitool","-i",hci,"cmd","0x08","0x0008", *hexbytes[:31]])  # up to 31
        # enable
        self._run(["/usr/bin/hcitool","-i",hci,"cmd","0x08","0x000a","01"])
        self._run(["/usr/bin/hciconfig", hci, "leadv", "3"])

    def _loop(self):
        interval = int(self.opts.get("interval_s", 20))
        _mark("loop_start")
        first = True
        while not self._stop.is_set():
            try:
                payload = self._build_payload()
                # Always use safe sequence (disable/params/data/enable)
                self._ble_set_adv(payload)
                _mark(f"tick v3 len={len(payload)}")
            except Exception as e:
                _mark(f"tick error: {e}")
            self._stop.wait(interval)


    def on_ui_update(self, ui):
        # Try common places where UI keeps the face name
        face = None
        for attr in ("state", "_state"):
            st = getattr(ui, attr, None)
            try:
                if isinstance(st, dict) and "face" in st:
                    face = st.get("face")
                    break
                if hasattr(st, "get"):
                    face = st.get("face")
                    if face is not None:
                        break
            except Exception:
                pass
        if isinstance(face, str) and face:
            self._last_face = face


# ---- Face extension (non-breaking, v4 payload) -------------------------------
try:
    # Map UI face name -> compact byte
    FACE_CODES = {
        "cool":1,"sleep":2,"angry":3,"sad":4,"friend":5,"smile":6,"excited":7,
        "look_r":8,"look_l":9,"intense":10,"smart":11,"bored":12,"happy":13,
        "grin":14,"monocle":15,"quiet":16,"shy":17,"evil":18,"awake":19,"debug":20
    }

    _orig_build = getattr(BLEBeacon, "_build_payload", None)
    if _orig_build and not getattr(BLEBeacon, "_face_ext_active", False):

        # Replace builder: force version=4 and append face byte
        def _build_payload_v4(self):
            base = _orig_build(self)
            if not base:
                return base
            b = bytearray(base)
            if b:
                b[0] = 4  # version -> 4
            face = getattr(self, "_last_face", "Unknown")
            code = FACE_CODES.get(face, 1)
            return bytes(b) + bytes([code])

        # Capture face name from UI updates
        def _on_ui_update(self, ui):
            face = None
            for attr in ("state", "_state"):
                st = getattr(ui, attr, None)
                try:
                    if isinstance(st, dict) and "face" in st:
                        face = st.get("face"); break
                    if hasattr(st, "get"):
                        face = st.get("face")
                        if face is not None:
                            break
                except Exception:
                    pass
            if isinstance(face, str) and face:
                self._last_face = face

        BLEBeacon._build_payload = _build_payload_v4
        BLEBeacon.on_ui_update = _on_ui_update
        BLEBeacon._face_ext_active = True
        try:
            LOGGER.info("ble_beacon: face extension active (v4 payload)")
        except Exception:
            pass
except Exception as e:
    try:
        LOGGER.exception("ble_beacon: face extension failed: %s", e)
    except Exception:
        pass
# ----------------------------------------------------------------------------- 


# ---- Global runtime patch: force 15B LE Set Adv Params for any subprocess ----
try:
    import os
    import subprocess as _sp

    def _ble_fix_args(av):
        # Normalize argv to a list of strings
        if isinstance(av, (list, tuple)):
            a = list(map(str, av))
        else:
            a = [str(av)]

        try:
            if not a:
                return av
            base = os.path.basename(a[0])
            if base == "hcitool":
                # Look for "... cmd 0x08 0x0006 ..."
                for i in range(len(a) - 2):
                    if a[i] == "cmd" and a[i+1] == "0x08" and a[i+2] == "0x0006":
                        # Replace with canonical 15-byte payload
                        fixed = a[:i+3] + [
                            "a0","00","a0","00",  # min/max = 100ms
                            "00",                 # adv type = ADV_IND
                            "00",                 # own addr = public
                            "00","00","00","00","00","00",  # direct addr zeros
                            "07",                 # channels 37,38,39
                            "00",                 # filter policy any
                        ]
                        try:
                            _mark("param-fix applied: " + " ".join(fixed))
                        except Exception:
                            pass
                        return fixed
        except Exception as e:
            try:
                _mark(f"param-fix error: {e}")
            except Exception:
                pass
        return av

    if not getattr(_sp, "_ble_param_fix_active", False):
        # Save originals
        _orig_run = getattr(_sp, "run", None)
        _orig_cc  = getattr(_sp, "check_call", None)
        _orig_co  = getattr(_sp, "check_output", None)
        _orig_popen = getattr(_sp, "Popen", None)

        # Wrap run / check_* if present
        if _orig_run:
            def _run_patched(args, *pa, **kw): return _orig_run(_ble_fix_args(args), *pa, **kw)
            _sp.run = _run_patched
        if _orig_cc:
            def _cc_patched(args, *pa, **kw): return _orig_cc(_ble_fix_args(args), *pa, **kw)
            _sp.check_call = _cc_patched
        if _orig_co:
            def _co_patched(args, *pa, **kw): return _orig_co(_ble_fix_args(args), *pa, **kw)
            _sp.check_output = _co_patched

        # Wrap Popen (many plugins use it)
        if _orig_popen:
            class _PopenPatched(_orig_popen):
                def __init__(self, args, *pa, **kw):
                    super().__init__(_ble_fix_args(args), *pa, **kw)
            _sp.Popen = _PopenPatched

        _sp._ble_param_fix_active = True
        try:
            _mark("subprocess param-fix hook active (run/check_*/Popen)")
        except Exception:
            pass
except Exception:
    pass
# ------------------------------------------------------------------------------
