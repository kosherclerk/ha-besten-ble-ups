"""Constants for the BestEn BLE UPS integration."""
from __future__ import annotations

DOMAIN = "besten_ble_ups"
NAME_PREFIX = "SC-160"
# The name is only in the scan response (needs active scanning); the main advertisement carries
# just this service UUID, so passive scanners (ESPHome/Shelly proxies) only see the UUID.
SERVICE_UUID = "0000ffe0-0000-1000-8000-00805f9b34fb"
MANUFACTURER = "BestEn"
MODEL = "SC-160A-C (BLE config)"

CONF_SCAN_INTERVAL = "scan_interval"
CONF_BATTERY_TYPE = "battery_type"
CONF_BATTERY_AH = "battery_capacity_ah"
CONF_BATTERY_BMS = "battery_bms"
CONF_BATTERY_VOLTAGE = "battery_voltage"
CONF_BATTERY_USABLE_PCT = "battery_usable_pct"
CONF_BATTERY_WH = "battery_usable_wh"  # v0.1.x, still honoured if no capacity is set
CONF_TYPICAL_LOAD = "typical_load_w"  # used for the runtime estimate until an outage measures the load

DEFAULT_SCAN_INTERVAL = 10  # seconds
MIN_SCAN_INTERVAL = 5
MAX_SCAN_INTERVAL = 300
CONFIG_REFRESH = 300  # seconds between reads of the configuration block

# An outage must last at least this long before its average load replaces the stored estimate.
MIN_OUTAGE_FOR_LOAD = 60
