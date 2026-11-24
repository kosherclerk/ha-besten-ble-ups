"""Battery profiles for the runtime estimate. Pure Python (no Home Assistant imports).

"Usable %" is the share of the rated energy you can expect before the UPS cuts off at a low
discharge rate (a few watts on a 12 V battery). The defaults are deliberately a little conservative:
  * LiFePO4 with BMS: 90 % (flat curve, nearly all capacity is above the UPS cutoff; keep a margin
    for ageing and the BMS low-voltage protection).
  * LiFePO4 without BMS: 80 % (the weakest cell limits the pack once cells drift out of balance).
  * AGM / GEL / flooded lead-acid: 70 % (the cutoff, ageing and temperature eat into capacity;
    deep discharges also shorten lead-acid life considerably).
"""
from __future__ import annotations

from dataclasses import dataclass

BATTERY_TYPES = ("lifepo4", "agm", "gel", "lead_acid")

RATED_VOLTAGE = {"lifepo4": 12.8, "agm": 12.0, "gel": 12.0, "lead_acid": 12.0}


def default_usable_pct(battery_type: str, has_bms: bool = True) -> int:
    if battery_type == "lifepo4":
        return 90 if has_bms else 80
    return 70


@dataclass(frozen=True)
class BatteryProfile:
    battery_type: str
    rated_voltage: float
    capacity_ah: float
    has_bms: bool
    usable_pct: float

    @property
    def rated_wh(self) -> float:
        return self.rated_voltage * self.capacity_ah

    @property
    def usable_wh(self) -> float:
        return self.rated_wh * self.usable_pct / 100


def select_load(live: float | None, measured: float | None, configured: float | None) -> tuple[float | None, str]:
    """Pick the load used for the runtime estimate: live (on battery) > measured (last outage) > configured.

    Returns (watts, source) where source is "live", "measured", "configured" or "none"."""
    for value, source in ((live, "live"), (measured, "measured"), (configured, "configured")):
        if value is not None and value > 0.5:
            return value, source
    return None, "none"


def runtime_hours(usable_wh: float, load_w: float | None, used_wh: float = 0.0) -> float | None:
    if usable_wh <= 0 or not load_w or load_w <= 0.5:
        return None
    return max(usable_wh - used_wh, 0.0) / load_w


def profile_from_options(options: dict) -> BatteryProfile | None:
    """Build the profile from config-entry options; supports the v0.1 'battery_usable_wh' option."""
    ah = float(options.get("battery_capacity_ah") or 0)
    if ah > 0:
        btype = options.get("battery_type", "lifepo4")
        bms = bool(options.get("battery_bms", True))
        return BatteryProfile(
            battery_type=btype,
            rated_voltage=float(options.get("battery_voltage") or RATED_VOLTAGE.get(btype, 12.0)),
            capacity_ah=ah,
            has_bms=bms,
            usable_pct=float(options.get("battery_usable_pct") or default_usable_pct(btype, bms)),
        )
    legacy_wh = float(options.get("battery_usable_wh") or 0)
    if legacy_wh > 0:  # v0.1.x option: usable energy entered directly
        return BatteryProfile("unknown", 1.0, legacy_wh, True, 100.0)
    return None
