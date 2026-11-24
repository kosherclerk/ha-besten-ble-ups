"""Polling coordinator: reads the UPS, tracks outages and the measured load."""
from __future__ import annotations

import logging
import time
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timedelta

from bleak.exc import BleakError

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .battery import BatteryProfile, profile_from_options, runtime_hours, select_load
from .const import (
    CONF_SCAN_INTERVAL,
    CONF_TYPICAL_LOAD,
    CONFIG_REFRESH,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MIN_OUTAGE_FOR_LOAD,
)
from .device import UpsDevice
from .protocol import ProtocolError, UpsConfig, UpsStatus

_LOGGER = logging.getLogger(__name__)

type BestenUpsConfigEntry = ConfigEntry["BestenUpsCoordinator"]


@dataclass
class UpsData:
    status: UpsStatus
    config: UpsConfig | None
    load_w: float | None  # live on battery > last measured outage average > configured typical load
    load_live: bool
    load_source: str  # "live" | "measured" | "configured" | "none"
    outage_start: datetime | None
    outage_energy_wh: float
    runtime_h: float | None
    battery: BatteryProfile | None


class BestenUpsCoordinator(DataUpdateCoordinator[UpsData]):
    """Polls the UPS over BLE.

    The UPS only reports battery current, so the load on its output is measurable only while
    running on battery (battery discharge power = load). The average of the last outage of
    at least a minute is kept as the load estimate on mains.
    """

    config_entry: BestenUpsConfigEntry

    def __init__(self, hass: HomeAssistant, entry: BestenUpsConfigEntry, device: UpsDevice) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{DOMAIN} {device.address}",
            update_interval=timedelta(seconds=float(entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL))),
        )
        self.battery = profile_from_options(dict(entry.options))
        self.device = device
        self.ups_config: UpsConfig | None = None
        self._config_read_at = 0.0
        self._outage_start: datetime | None = None
        self._outage_wh = 0.0
        self._last_sample: datetime | None = None
        self._recent_load: deque[float] = deque(maxlen=6)
        self.load_estimate: float | None = None  # W, restored by the load sensor after restarts

    async def _async_update_data(self) -> UpsData:
        try:
            status = await self.device.read_status()
            if self.ups_config is None or time.monotonic() - self._config_read_at > CONFIG_REFRESH:
                self.ups_config = await self.device.read_config()
                self._config_read_at = time.monotonic()
        except (BleakError, ProtocolError, TimeoutError) as err:
            raise UpdateFailed(f"Error reading UPS {self.device.address}: {err}") from err

        now = dt_util.utcnow()
        self._track_outage(status, now)

        live = sum(self._recent_load) / len(self._recent_load) if status.on_battery and self._recent_load else None
        configured = float(self.config_entry.options.get(CONF_TYPICAL_LOAD) or 0) or None
        load, source = select_load(live, self.load_estimate, configured)

        usable_wh = self.battery.usable_wh if self.battery else 0.0
        runtime = runtime_hours(usable_wh, load, self._outage_wh if status.on_battery else 0.0)

        return UpsData(
            status=status,
            config=self.ups_config,
            load_w=round(load, 2) if load is not None else None,
            load_live=source == "live",
            load_source=source,
            outage_start=self._outage_start,
            outage_energy_wh=round(self._outage_wh, 3),
            runtime_h=round(runtime, 2) if runtime is not None else None,
            battery=self.battery,
        )

    def _track_outage(self, status: UpsStatus, now: datetime) -> None:
        dt = (now - self._last_sample).total_seconds() if self._last_sample else 0.0
        self._last_sample = now
        if status.on_battery:
            if self._outage_start is None:
                self._outage_start, self._outage_wh = now, 0.0
                self._recent_load.clear()
                _LOGGER.info("%s: AC power lost, running on battery", self.device.address)
            discharge = -status.battery_power
            if discharge > 0:
                self._recent_load.append(discharge)
                if 0 < dt <= 120:  # don't integrate across long gaps
                    self._outage_wh += discharge * dt / 3600
        elif self._outage_start is not None:
            duration = (now - self._outage_start).total_seconds()
            if duration >= MIN_OUTAGE_FOR_LOAD and self._outage_wh > 0:
                self.load_estimate = self._outage_wh * 3600 / duration
            _LOGGER.info("%s: AC power restored after %.0f s (%.2f Wh from battery)",
                         self.device.address, duration, self._outage_wh)
            self._outage_start = None
            self._outage_wh = 0.0
            self._recent_load.clear()
