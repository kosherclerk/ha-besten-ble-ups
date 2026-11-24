"""Diagnostics: raw registers to help decode more of the protocol."""
from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_ADDRESS
from homeassistant.core import HomeAssistant

from .coordinator import BestenUpsConfigEntry
from .protocol import CONFIG_BASE, STATUS_BASE

TO_REDACT = {CONF_ADDRESS, "unique_id", "title"}


async def async_get_config_entry_diagnostics(hass: HomeAssistant, entry: BestenUpsConfigEntry) -> dict[str, Any]:
    data = entry.runtime_data.data
    status = data.status if data else None
    config = data.config if data else None
    return {
        "entry": async_redact_data(entry.as_dict(), TO_REDACT),
        "status_registers": {f"0x{STATUS_BASE + i:04X}": v for i, v in enumerate(status.raw)} if status else None,
        "config_registers": {f"0x{CONFIG_BASE + i:04X}": v for i, v in enumerate(config.raw)} if config else None,
        "load_w": data.load_w if data else None,
        "load_live": data.load_live if data else None,
    }
