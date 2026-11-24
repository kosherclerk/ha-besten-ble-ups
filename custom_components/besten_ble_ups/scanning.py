"""Helpers for Home Assistant's Bluetooth scanning mode.

The UPS is only visible to HA while a scanner runs in ACTIVE mode on many adapters (in passive
mode a local BlueZ adapter may report no advertisements at all). HA's default for local adapters
is AUTO (passive, promoted to active on demand), so:

1. we ask HA for an on-demand active sweep (`async_request_active_scan`, HA with AUTO support);
2. if that is not enough, the setup flow offers to switch local adapters to ACTIVE, with consent.
"""
from __future__ import annotations

import logging

from homeassistant.components import bluetooth
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .scanmode import OPT_LEGACY_PASSIVE, OPT_MODE, scanning_mode

__all__ = ["ACTIVE_SWEEP_SECONDS", "async_active_sweep", "async_set_adapters_active",
           "non_active_local_adapters", "scanning_mode"]

_LOGGER = logging.getLogger(__name__)

BT_DOMAIN = "bluetooth"
ACTIVE_SWEEP_SECONDS = 15


def non_active_local_adapters(hass: HomeAssistant) -> list[ConfigEntry]:
    """Local adapters (not ESPHome/remote proxies) that are not in ACTIVE mode."""
    return [
        entry
        for entry in hass.config_entries.async_entries(BT_DOMAIN)
        if not entry.data.get("source")  # remote scanners carry their source; leave them alone
        and scanning_mode(dict(entry.options)) != "active"
    ]


async def async_active_sweep(hass: HomeAssistant, seconds: float = ACTIVE_SWEEP_SECONDS) -> bool:
    """Ask HA for an on-demand active scan on AUTO scanners. Returns False if HA has no such API."""
    request = getattr(bluetooth, "async_request_active_scan", None)
    if request is None:
        return False
    try:
        await request(hass, seconds)
    except Exception:  # noqa: BLE001 - never let discovery help break setup
        _LOGGER.debug("Active scan request failed", exc_info=True)
        return False
    return True


async def async_set_adapters_active(hass: HomeAssistant, entries: list[ConfigEntry]) -> None:
    """Switch the given local adapters to ACTIVE scanning (user consented) and reload them."""
    for entry in entries:
        _LOGGER.info("Switching Bluetooth adapter %s to active scanning (user consent)", entry.title)
        hass.config_entries.async_update_entry(
            entry, options={**entry.options, OPT_MODE: "active", OPT_LEGACY_PASSIVE: False}
        )
        await hass.config_entries.async_reload(entry.entry_id)
