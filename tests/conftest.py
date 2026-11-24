"""Load the integration's HA-independent modules without importing Home Assistant."""
import importlib
import sys
import types
from pathlib import Path

PKG_DIR = Path(__file__).resolve().parent.parent / "custom_components" / "besten_ble_ups"


def load(module: str):
    """Import custom_components/besten_ble_ups/<module>.py as part of a stub package
    (skips the package __init__, which needs Home Assistant)."""
    if "bbu" not in sys.modules:
        pkg = types.ModuleType("bbu")
        pkg.__path__ = [str(PKG_DIR)]
        sys.modules["bbu"] = pkg
    return importlib.import_module(f"bbu.{module}")
