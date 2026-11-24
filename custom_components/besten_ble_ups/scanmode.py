"""Resolve a Home Assistant Bluetooth adapter's scanning mode from its config-entry options.

Pure Python (no Home Assistant imports) so it can be unit-tested. Mirrors
homeassistant.components.bluetooth.util.resolve_scanning_mode: the "mode" option
("auto" | "active" | "passive") wins; otherwise the legacy boolean "passive"; default "auto".
"""
from __future__ import annotations

from typing import Any

OPT_MODE = "mode"
OPT_LEGACY_PASSIVE = "passive"
MODES = ("auto", "active", "passive")


def scanning_mode(options: dict[str, Any]) -> str:
    mode = options.get(OPT_MODE)
    if mode in MODES:
        return mode
    legacy = options.get(OPT_LEGACY_PASSIVE)
    if legacy is True:
        return "passive"
    if legacy is False:
        return "active"
    return "auto"
