# BestEn SC-160A-C BLE protocol notes

This was reverse-engineered on one unit (firmware 21900102, software 20250107). The vendor's configuration app is a private WeChat mini-program, and no official documentation was available.

## Device

The UPS is a switch-mode 12 V DC UPS for an external 12 V battery:
- AC input 85–264 V.
- Output about 13.8–14.5 V, following the battery.
- 160 W total, shared between the load and the charger.
- Charge current adjustable from 0 to 11.6 A over BLE (default 6 A).
- Supports AGM, GEL and LiFePO4 batteries.

## BLE

- Advertised name: `SC-160A-C-BLE-R01`. GAP name: "Baymax BLE Rev1.0".
- Device Information service: manufacturer "ZYG Power", model "ZYG UPS Power BLE".
- Service `FFE0`:
  - `FFE1` (read/write), user description "Characteristic -- Modbus".
  - `FFE2` (read/write), user description "Characteristic -- Login". Not needed for anything below.
- **Only one central can be connected at a time.**

## Modbus tunnel

- Write a Modbus RTU request (CRC16, slave `0x01`) to `FFE1`, then **read** `FFE1` to get the reply. There's no notify.
- `0x03` (read holding registers) works, up to about 48 registers per request.
  - `0x04` and other slave addresses get no reply.
  - Unmapped registers read as 0, not as an exception.
- Writes: `0x10` (write multiple registers) works and is acknowledged. `0x06` is **silently ignored**. No login was required. *(This integration doesn't write.)*
- A full scan of 0x0000–0xFFFF found data only in **0x1000–0x102F** and **0x7000–0x7033**.

## Status registers (0x1000+)

Confidence: **C** confirmed by tests, **L** likely, **G** guess, **?** unknown.

| Reg | Meaning | Scale | Conf. | Evidence |
|---|---|---|---|---|
| 0x1001–02 | Firmware (hex words, e.g. `2190 0102`) | | L | Matches Device Information |
| 0x1005–06 | Software date (`2025 0107`) | | L | |
| 0x1007–08 | Uptime, u32 seconds | 1 s | C | Advanced 6201 counts in 6202 s; keeps counting on battery |
| 0x100A | Power source: 5 = mains, 4 = battery | | C | AC unplug tests |
| 0x100C | Alarm flags; bit 4 = AC lost | | L | |
| 0x1010 | Constant 13 | | ? | |
| 0x1011 | Battery voltage | 0.01 V | L | Smooth discharge and charge curves |
| 0x1012 / 0x1014 | ≈ 6.85 × 0x1011 / 0x1013 | | ? | Raw ADC or state of charge? |
| 0x1013 | Output voltage | 0.01 V | G | Always 0.01–0.05 V below the battery |
| 0x1015 | 0x1016 ÷ ≈16.8 (signed) | | ? | |
| 0x1016 | Battery current, signed, + = charging | 0.001 A | discharge L / charge ✗ | Discharge: steady 7–9 W, 1 W load steps visible. Charge: over-reads, offset at float |
| 0x1017 | Present only on mains (~137); dips slightly with lower load | | ? | |
| 0x1019–1A, 0x1020–21 | Regulator internals | | ? | |
| 0x101B | Changes only a few seconds after AC returns | | ? | Not AC voltage |
| 0x101C | 12 mains / 22 battery | | G | |
| 0x101D | 39 at float; 22 → 33 → 35 when AC returns | | ? | Linked to the charger starting up |
| 0x101F | Temperature | 0.1 °C | G | Stable, plausible |
| 0x1022 | Charge-stage setpoint | 0.01 A | C | Ramps to the 0x7012 value after AC returns; 6 % of it at float |
| 0x1023 | 25 × 0x1022 | | L | |
| 0x1026–29 | The module's BLE MAC address | | C | |

## Configuration registers (0x7000+)

| Reg | Factory | Meaning | Conf. |
|---|---|---|---|
| 0x7008 | 1 | Battery type / mode? | ? |
| 0x700A | 9600 | Serial baud rate? | G |
| 0x700E | 1450 | Charge (CV) voltage, 0.01 V | L (observed CV 14.48–14.52 V) |
| 0x700F | 400 | 4.00 A? | ? |
| 0x7011 | 1460 | Maximum battery voltage, 0.01 V | G |
| 0x7012 | 600 | **Charge-current setting, 0.01 A** | C: drives 0x1022. Effect on real current not measured |
| 0x7014–19 | 10200, 7123, 200, 11000, 30000, 1000 | 0x7017 may be the low-voltage cutoff (11.000 V) | ? |
| 0x7021–2E | … | Look like factory calibration. **Do not write** | |
| 0x7033 | 2 | | ? |

Contributions with measurements (multimeter or DC clamp readings next to register values) are very welcome.
