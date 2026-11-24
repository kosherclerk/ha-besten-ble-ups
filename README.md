# BestEn BLE UPS for Home Assistant

A custom integration for the **BestEn SC-160A-C (BLE config)** 12 V DC UPS. It reads the UPS over Bluetooth LE: power source, battery voltage, battery current and power, load, estimated runtime, and more.

Works with the host's Bluetooth adapter or with **ESPHome Bluetooth proxies** (active connections).

> **Unofficial.** Not affiliated with BestEn or the BLE module maker. The protocol was reverse-engineered from a real unit (see [docs/PROTOCOL.md](docs/PROTOCOL.md)). The integration is **read-only**: it never changes UPS settings.

## Features

| Entity | Type | Notes |
|---|---|---|
| AC power | binary sensor (power) | Off during a power outage |
| Charging | binary sensor (battery charging) | On while the battery is noticeably charging after an outage |
| Power source | sensor (enum) | `mains` / `battery` |
| Battery voltage | sensor (V) | |
| Output voltage | sensor (V) | Follows the battery voltage (≈ 14.5 V on mains) |
| Battery current | sensor (A) | Negative = discharging. **Charging values are uncalibrated** (see below) |
| Battery power | sensor (W) | Battery voltage × current |
| Load power | sensor (W) | Live while on battery; on mains, the average from the last outage (kept across restarts) |
| Estimated runtime | sensor (h) | **Time left** while on battery; full-battery runtime on mains. Needs the battery described in Options |
| Temperature | diagnostic (°C) | Reported by the UPS; not verified against a thermometer |
| Charge stage setpoint | diagnostic (A) | Equals the charge-current setting during bulk charging, about 6 % of it at float |
| Charge current setting | diagnostic (A) | The UPS's configured charge current (factory 6.00 A) |
| Charge voltage setting | diagnostic (V) | Disabled by default |
| Last restart | diagnostic (timestamp) | When the UPS electronics last powered up |

Diagnostics downloads include all raw registers, to help decode more of the protocol.

### Limitations (please read)

- **One connection at a time.** The UPS accepts a single Bluetooth client. While Home Assistant is connected, a phone or other tool can't connect, and the other way round.
- **No AC voltage, and no load current on mains.** The UPS doesn't report them. The load is measured from the battery during outages (battery discharge power = load).
- **Charging-current readings are not reliable.** Discharge readings are consistent and sensitive to about 1 W. While charging, the UPS over-reports current and shows about +0.5–0.7 A even when the battery is full.
- Tested with one unit: firmware `21900102`, BLE name `SC-160A-C-BLE-R01`. Other BestEn/ZYG models with the same BLE module may work. Reports are welcome.

## Installation

### HACS (recommended)

1. HACS → ⋮ → **Custom repositories** → add `https://github.com/kosherclerk/ha-besten-ble-ups`, category **Integration**.
2. Install **BestEn BLE UPS** and restart Home Assistant.

### Manual

Copy `custom_components/besten_ble_ups` to `<config>/custom_components/` and restart Home Assistant.

## Setup

1. Make sure no phone or other app is connected to the UPS.
2. The UPS is usually **discovered automatically** (Settings → Devices & services → *Discovered*). Otherwise use **Add integration → BestEn BLE UPS** and pick it from the list. Both active and passive Bluetooth scanning work.
3. The integration does a quick test read, then asks about **your battery** on the same screen sequence: **type** (LiFePO4 / AGM / GEL / other lead-acid), **rated capacity (Ah)** from the label, **built-in BMS**, and optionally your **typical load (W)**. Rated voltage and usable share are filled in from the type. That's all: the estimated runtime works right away.

To change anything later, use **Configure**. It includes the update interval (default 10 s), plus a second step to fine-tune rated voltage and usable share. It shows the resulting usable energy.

   | Battery | Default rated voltage | Default usable share |
   |---|---|---|
   | LiFePO4 with BMS | 12.8 V | 90 % |
   | LiFePO4 without BMS | 12.8 V | 80 % |
   | AGM / GEL / other lead-acid | 12.0 V | 70 % |

   Example: LiFePO4 30 Ah with BMS → 12.8 V × 30 Ah × 90 % ≈ **346 Wh** usable.

**How the runtime estimate works:** while on battery it shows the **time left**: (usable energy − energy used in this outage) ÷ live load. On mains it shows how long a full battery would last. It uses the load **measured** in the last outage of at least one minute, or the **typical load** from Configure if no outage has been measured yet. The `source` attribute of *Load power* says which. Unplug the UPS from mains for a couple of minutes once to measure your real load.

## Troubleshooting

**"No BestEn SC-160 UPS seen over Bluetooth"**
1. **Disconnect everything else.** While a phone, a PC tool or another Home Assistant is connected, the UPS **stops advertising** and can't be found. Disconnect it and wait about a minute.
2. **Check that Home Assistant hears it:** Settings → Bluetooth → *Advertisement monitor*. Look for a device advertising service `0000ffe0-…`.
   - With **passive** scanning (the default "Auto" on many installs, ESPHome or Shelly proxies) the UPS shows **without a name**. That's fine: it's found through its FFE0 service and added as "BestEn UPS xx:xx".
   - With **active** scanning (optional) its name `SC-160A-C-BLE-R01` also appears. If discovery doesn't work in passive mode, try Settings → Devices & services → **Bluetooth** → your adapter → **Configure** → scanning mode **Active**.
3. **Range:** BLE through a metal rack is short. An ESPHome Bluetooth proxy (`bluetooth_proxy: active: true`) near the UPS helps a lot. Active connections must be enabled on the proxy.

Before a device is added, the integration does a real Modbus read. A different FFE0 gadget is rejected with "not supported".

## Example automation

```yaml
automation:
  - alias: "UPS on battery"
    triggers:
      - trigger: state
        entity_id: binary_sensor.sc_160a_c_ble_r01_ac_power
        to: "off"
    actions:
      - action: notify.notify
        data:
          message: >
            Power outage, the UPS is on battery
            ({{ states('sensor.sc_160a_c_ble_r01_estimated_runtime') }} h left).
```

## Development

```bash
pip install pytest bleak bleak-retry-connector
pytest tests
```

The protocol and BLE transport (`protocol.py`, `device.py`) don't depend on Home Assistant.

## License

MIT
