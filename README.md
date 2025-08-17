# Pwnagotchi ↔ Home Assistant (BLE bridge)

Expose Pwnagotchi stats to Home Assistant **without Wi‑Fi or USB tethering** by broadcasting a tiny BLE Manufacturer packet from the Pi and consuming it with a lightweight Home Assistant custom component that works with **ESPHome Bluetooth Proxies**.

This repo contains:

```
.
├─ pwnagotchi/ble_beacon.py                 # Pwnagotchi plugin (BLE advertiser)
├─ homeassistant/custom_components/
│  └─ pwnagotchi_ble/                       # HA integration (passive BLE)
│     ├─ __init__.py
│     ├─ manifest.json
│     ├─ config_flow.py
│     ├─ sensor.py
│     └─ binary_sensor.py
└─ README.md
```

---

## Why

* Pwnagotchi typically has **no network** while roaming. BLE is available.
* Home Assistant already has a great **passive BLE pipeline**, including ESPHome proxies distributed around the house.
* A tiny, read‑only BLE advertisement is enough to surface useful sensors: epochs, handshakes, battery, CPU temp, etc.

---

## Quick start

### 1) Pwnagotchi (Pi) — install & enable the plugin

1. Copy `pwnagotchi/ble_beacon.py` to the Pi:

   ```bash
   sudo mkdir -p /usr/local/share/pwnagotchi/custom-plugins
   sudo cp ble_beacon.py /usr/local/share/pwnagotchi/custom-plugins/
   sudo chown root:root /usr/local/share/pwnagotchi/custom-plugins/ble_beacon.py
   sudo chmod 644 /usr/local/share/pwnagotchi/custom-plugins/ble_beacon.py
   ```
2. Enable custom plugins & the beacon in `/etc/pwnagotchi/config.toml`:

   ```toml
   main.custom_plugins = "/usr/local/share/pwnagotchi/custom-plugins"
   main.plugins.ble_beacon.enabled = true
   ```
3. Restart Pwnagotchi:

   ```bash
   sudo systemctl restart pwnagotchi
   ```

### 2) Home Assistant — install the custom component

1. Copy the folder `homeassistant/custom_components/pwnagotchi_ble/` into your HA `config/custom_components/` directory (or upload the provided ZIP and extract there).
2. Restart Home Assistant.
3. Go to **Settings → Devices & Services** and accept the **Discovered: Pwnagotchi BLE** card.

You’ll get sensors for: **RSSI**, **Last Seen**, **Payload (hex)**, plus decoded values (Handshakes, Points, Epochs, CPU Temp, Battery %, Charging, Age/Strength indexes).

---

## What gets broadcast

The plugin advertises a single BLE Legacy (ADV\_IND) frame with Manufacturer ID **0xFFFF** and this payload schema (little‑endian):

```
<BHHHBBBBB>
ver, handshakes, points, epochs, temp_x2, battery_pct, flags, age_idx, strength_idx
```

* `ver` = 1 (frame version)
* `temp_x2 / 2.0` = CPU Temp in °C
* `battery_pct` = 0–100; **255** = unknown
* `flags bit0` = 1 when **charging**
* `age_idx`, `strength_idx` = small indexes you can map to labels in HA templates (optional)

> Advertising interval is configurable; **20 s** recommended for normal use. The code ships with a debug diag file at `/tmp/ble_beacon.diag` that logs key events.

---

## Requirements & notes

* **Pi with Bluetooth** (Raspberry Pi 0W/3/4/5, etc.). BlueZ (`bluez`, `pi-bluetooth`) should already be installed on Pwnagotchi images.
* The plugin uses `/usr/bin/hcitool` and `/usr/bin/hciconfig` directly for broad compatibility. (Yes, they’re old; mgmt APIs could replace them later.)
* Works with **multiple ESPHome Bluetooth Proxies**; HA merges advertisements — no single proxy lock‑in.
* No pairing, no connections, no Wi‑Fi required.

---

## Verifying the Pi side

1. Confirm the adapter is up:

   ```bash
   hciconfig -a
   bluetoothctl show
   rfkill list
   ```
2. Start Pwnagotchi and tail the plugin diag:

   ```bash
   sudo systemctl restart pwnagotchi
   sudo tail -f /tmp/ble_beacon.diag
   # expected lines: on_loaded, loop_start, tick, run: ... 0x0006/0x0008/0x000a
   ```
3. For definitive HCI tracing:

   ```bash
   sudo btmon
   # in another shell, restart pwnagotchi to capture the sequence
   # Expected order: Disable → Set Adv Params (Success) → Set Adv Data (Success) → Enable (Success)
   ```

### Common gotchas

* **Command Disallowed (0x0c)** on enable → something else is advertising. The plugin disables first, but you can sanitize manually:

  ```bash
  sudo bluetoothctl advertise off || true
  sudo btmgmt -i hci0 advertising off || true
  sudo btmgmt -i hci0 power on; sudo btmgmt -i hci0 le on
  sudo systemctl restart pwnagotchi
  ```
* Seeing two MACs in HA? One is the public Pi MAC, the other a private/random MAC. To stick to the public address only:

  ```bash
  sudo btmgmt -i hci0 privacy off
  sudo systemctl restart pwnagotchi
  ```

---

## Verifying in Home Assistant

* Use **Settings → Devices & Services → Bluetooth → Advertisement monitor**. Look for your Pi’s MAC and *Manufacturer: 0xFFFF*.
* The custom component matches on manufacturer `65535` and first payload byte `0x01` (version), then creates/updates a device named after the advert’s local name (e.g., `StratoGotchi`).

### Entities created

* **Sensors:**

  * *Pwnagotchi RSSI* (dBm)
  * *Pwnagotchi Last Seen* (timestamp)
  * *Pwnagotchi Payload (hex)* (debug)
  * *Pwnagotchi Handshakes* (total increasing)
  * *Pwnagotchi Points*
  * *Pwnagotchi Epochs*
  * *Pwnagotchi CPU Temp* (°C)
  * *Pwnagotchi Battery* (%) — becomes `unknown` if payload says 255
  * *Pwnagotchi Age Index* (hidden by default)
  * *Pwnagotchi Strength Index* (hidden by default)
* **Binary sensor:**

  * *Pwnagotchi Charging*

> Tip: Add the device to a dashboard; the useful ones are Last Seen, Battery, CPU Temp, Epochs/Handshakes.

---

## Optional: show the Pwnagotchi face in HA

If your Pwnagotchi is reachable on your LAN (e.g., you’ve given it Wi‑Fi or USB‑tethered to the HA host), add a **Webpage** card pointing to the UI:

* URL: `http://<pwnagotchi-ip>:8080/`
  (The root page renders the virtual display.)

This is independent from BLE and doesn’t affect proxies.

---

## Configuration (advanced)

The plugin has these defaults (can be overridden if you add an `options` block in the Pwnagotchi config’s plugin section):

```python
DEFAULTS = {
    "interval_s": 20,            # Set to 5 while testing only
    "age_json": "/root/age_strength.json",
    "company_id": 0xFFFF,        # Override if you have your own company ID
    "hci": "hci0",
    "enable_battery": True,      # Reads PiSugar JSON at pisugar_url if present
    "pisugar_url": "http://127.0.0.1:8421/status",
}
```

> If PiSugar isn’t installed, battery becomes `unknown` (255) and `charging` is `false`.

---

## Security & privacy

* BLE advertisements are **broadcast**. Anyone in range can decode your payload. It’s only counters/temps by default.
* If that’s a concern, reduce content, change `company_id`, or randomize addresses (BlueZ privacy on). Proxies will still forward.

---

## Development notes

* The plugin sends legacy HCI commands via `hcitool` to maximize compatibility on older kernels/BlueZ packaged with many Pwnagotchi images. A future version can migrate to `btmgmt` or `pydbus` mgmt APIs.
* The HA integration uses the **passive update processor**, so it never connects — it simply consumes frames merged from all adapters/proxies.

---

## Troubleshooting checklist

* **Pi**: `/tmp/ble_beacon.diag` shows `loop_start` and periodic `tick` lines; `btmon` shows `0x0006/0x0008/0x000a` sequence with **Status: Success**.
* **HA**: Discovered card appears; entity values update every `interval_s` seconds; RSSI fluctuates.
* If HA logs `unexpected keyword argument 'inactive_sleep_interval'`, you’re on an older HA build — use the provided compatible version (we omit that arg).

---

## Roadmap

* Optional **scan response** to carry the full local name (avoid truncation like `StratoGotc`).
* Optional **encryption/obfuscation** of payload.
* Camera entity that proxies the Pwnagotchi UI PNG.

---

## License

MIT for both plugin and custom component. See headers in source files.

---

## Credits

* Idea & implementation: you 🐧
* Pwnagotchi project: [https://github.com/evilsocket/pwnagotchi](https://github.com/evilsocket/pwnagotchi)
* Home Assistant BLE stack & ESPHome Bluetooth Proxy

---

## Appendix A — Manual BT cleanup commands

When testing, it helps to make sure nothing else is advertising:

```bash
sudo bluetoothctl advertise off || true
sudo btmgmt -i hci0 advertising off || true
sudo btmgmt -i hci0 power on
sudo btmgmt -i hci0 le on
```

## Appendix B — Expected HCI sequence (good case)

```
LE Set Advertise Enable … Disabled (Success)
LE Set Advertising Parameters … Success
LE Set Advertising Data … Success
LE Set Advertise Enable … Enabled (Success)
```
