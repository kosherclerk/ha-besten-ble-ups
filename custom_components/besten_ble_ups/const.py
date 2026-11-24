"""Constants for the BestEn BLE UPS integration."""
from __future__ import annotations

DOMAIN = "besten_ble_ups"
NAME_PREFIX = "SC-160"
MANUFACTURER = "BestEn"
MODEL = "SC-160A-C (BLE config)"

CONF_SCAN_INTERVAL = "scan_interval"
CONF_BATTERY_WH = "battery_usable_wh"
DEFAULT_SCAN_INTERVAL = 10  # seconds
MIN_SCAN_INTERVAL = 5
MAX_SCAN_INTERVAL = 300
CONFIG_REFRESH = 300  # seconds between reads of the configuration block

# An outage must last at least this long before its average load replaces the stored estimate.
MIN_OUTAGE_FOR_LOAD = 60
