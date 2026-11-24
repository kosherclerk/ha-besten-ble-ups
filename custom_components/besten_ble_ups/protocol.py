"""Modbus-over-BLE protocol for BestEn SC-160A-C (BLE config) DC UPS units.

Pure Python, no Home Assistant imports, so it can be unit-tested on its own.

The UPS exposes a "ZYG UPS Power BLE" module. Service 0xFFE0, characteristic 0xFFE1
("Characteristic -- Modbus") tunnels Modbus RTU: write a request frame, then READ the
characteristic to get the reply (there is no notify). Slave address 0x01.
Live status lives in holding registers 0x1000-0x102F, configuration in 0x7000-0x7033.

This module only builds READ requests (function 0x03).
"""
from __future__ import annotations

from dataclasses import dataclass, field

MODBUS_CHAR_UUID = "0000ffe1-0000-1000-8000-00805f9b34fb"
SLAVE = 0x01
READ_HOLDING = 0x03
MAX_REGS_PER_REQUEST = 48  # fits the module's 124-byte MTU

STATUS_BASE, STATUS_COUNT = 0x1000, 48
CONFIG_BASE, CONFIG_COUNT = 0x7000, 52

POWER_SOURCE_MAINS = 5
POWER_SOURCE_BATTERY = 4
ALARM_AC_LOST_BIT = 0x10


class ProtocolError(Exception):
    """Malformed or unexpected Modbus reply."""


def crc16(data: bytes) -> int:
    crc = 0xFFFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            crc = (crc >> 1) ^ 0xA001 if crc & 1 else crc >> 1
    return crc


def build_read(register: int, count: int) -> bytes:
    """Modbus RTU 'read holding registers' request."""
    if not 0 <= register <= 0xFFFF or not 1 <= count <= MAX_REGS_PER_REQUEST:
        raise ValueError("register range out of bounds")
    body = bytes([SLAVE, READ_HOLDING, register >> 8, register & 0xFF, 0, count])
    crc = crc16(body)
    return body + bytes([crc & 0xFF, crc >> 8])


def parse_read_reply(reply: bytes, count: int) -> list[int]:
    """Validate a 'read holding registers' reply and return the register values."""
    if len(reply) < 5:
        raise ProtocolError(f"short reply ({len(reply)} bytes)")
    if reply[0] != SLAVE:
        raise ProtocolError(f"unexpected slave address {reply[0]}")
    if reply[1] == READ_HOLDING | 0x80:
        raise ProtocolError(f"modbus exception code {reply[2]}")
    if reply[1] != READ_HOLDING:
        raise ProtocolError(f"unexpected function 0x{reply[1]:02x}")
    size = reply[2]
    if size != count * 2 or len(reply) != 3 + size + 2:
        raise ProtocolError(f"length mismatch (byte count {size}, frame {len(reply)})")
    if crc16(reply[:-2]) != int.from_bytes(reply[-2:], "little"):
        raise ProtocolError("CRC mismatch")
    data = reply[3:-2]
    return [int.from_bytes(data[i : i + 2], "big") for i in range(0, size, 2)]


def _s16(value: int) -> int:
    return value - 0x10000 if value & 0x8000 else value


@dataclass
class UpsStatus:
    """Decoded live status (registers 0x1000-0x102F).

    Field reliability, from tests on real hardware:
      power_source / on_battery / ac_lost  - confirmed (AC unplug tests)
      battery_voltage, output_voltage      - consistent, ×0.01 V
      battery_current, battery_power       - DISCHARGE side consistent and sensitive to ~1 W;
                                             CHARGE side is uncalibrated (over-reads, has a
                                             ~+0.7 A offset at float)
      charge_stage                         - follows the charge-current setting (0x7012);
                                             float value = 6 % of it
      temperature                          - plausible (×0.1 °C), not instrument-checked
      uptime                               - confirmed seconds since the module powered up
    """

    raw: list[int] = field(repr=False)
    power_source_code: int
    on_battery: bool
    ac_lost: bool
    battery_voltage: float
    output_voltage: float
    battery_current: float
    battery_power: float
    charge_stage: float
    temperature: float
    uptime: int
    firmware: str

    @property
    def power_source(self) -> str | None:
        return {POWER_SOURCE_MAINS: "mains", POWER_SOURCE_BATTERY: "battery"}.get(self.power_source_code)

    @property
    def charging(self) -> bool:
        # The charge side reads ~+0.7 A even when the battery is full, so use a margin.
        return not self.on_battery and self.battery_current > 1.0


def decode_status(regs: list[int]) -> UpsStatus:
    if len(regs) < STATUS_COUNT:
        raise ProtocolError("status block too short")
    r = lambda addr: regs[addr - STATUS_BASE]  # noqa: E731
    battery_voltage = r(0x1011) / 100
    battery_current = _s16(r(0x1016)) / 1000
    return UpsStatus(
        raw=list(regs),
        power_source_code=r(0x100A),
        on_battery=r(0x100A) == POWER_SOURCE_BATTERY,
        ac_lost=bool(r(0x100C) & ALARM_AC_LOST_BIT),
        battery_voltage=battery_voltage,
        output_voltage=r(0x1013) / 100,
        battery_current=battery_current,
        battery_power=round(battery_voltage * battery_current, 2),
        charge_stage=r(0x1022) / 100,
        temperature=r(0x101F) / 10,
        uptime=(r(0x1007) << 16) | r(0x1008),
        firmware=f"{r(0x1001):04X}{r(0x1002):04X}",
    )


@dataclass
class UpsConfig:
    """Decoded configuration block (registers 0x7000-0x7033). Meanings are partly inferred."""

    raw: list[int] = field(repr=False)
    charge_current: float  # 0x7012, confirmed to drive the charge controller
    charge_voltage: float  # 0x700E, likely (observed CV matches)
    max_battery_voltage: float  # 0x7011, guess


def decode_config(regs: list[int]) -> UpsConfig:
    if len(regs) < CONFIG_COUNT:
        raise ProtocolError("config block too short")
    r = lambda addr: regs[addr - CONFIG_BASE]  # noqa: E731
    return UpsConfig(
        raw=list(regs),
        charge_current=r(0x7012) / 100,
        charge_voltage=r(0x700E) / 100,
        max_battery_voltage=r(0x7011) / 100,
    )
