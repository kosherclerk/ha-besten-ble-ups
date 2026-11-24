import pytest

from conftest import load

p = load("protocol")


def reply(values: list[int]) -> bytes:
    body = bytes([0x01, 0x03, len(values) * 2]) + b"".join(v.to_bytes(2, "big") for v in values)
    c = p.crc16(body)
    return body + bytes([c & 0xFF, c >> 8])


def status_block(over: dict[int, int] | None = None) -> list[int]:
    regs = [0] * p.STATUS_COUNT
    base = {
        0x1001: 0x2190, 0x1002: 0x0102, 0x1007: 0x008B, 0x1008: 0x6548,
        0x100A: 5, 0x1011: 1448, 0x1013: 1447, 0x1016: 700, 0x101F: 334, 0x1022: 36,
    }
    base.update(over or {})
    for addr, v in base.items():
        regs[addr - p.STATUS_BASE] = v
    return regs


def test_crc_and_read_request():
    # Known-good request accepted by the hardware.
    assert p.build_read(0x1000, 16).hex(" ") == "01 03 10 00 00 10 40 c6"
    assert p.build_read(0x7000, 48)[:6] == bytes([1, 3, 0x70, 0, 0, 48])


@pytest.mark.parametrize("reg,count", [(-1, 1), (0x10000, 1), (0x1000, 0), (0x1000, 49)])
def test_build_read_bounds(reg, count):
    with pytest.raises(ValueError):
        p.build_read(reg, count)


def test_parse_reply_roundtrip():
    vals = list(range(1, 17))
    assert p.parse_read_reply(reply(vals), 16) == vals


def test_parse_reply_rejects_bad_crc():
    bad = bytearray(reply([1, 2]))
    bad[-1] ^= 0xFF
    with pytest.raises(p.ProtocolError, match="CRC"):
        p.parse_read_reply(bytes(bad), 2)


def test_parse_reply_rejects_wrong_length_and_exception():
    with pytest.raises(p.ProtocolError, match="length"):
        p.parse_read_reply(reply([1, 2, 3]), 2)
    exc = bytes([0x01, 0x83, 0x02])
    c = p.crc16(exc)
    with pytest.raises(p.ProtocolError, match="exception"):
        p.parse_read_reply(exc + bytes([c & 0xFF, c >> 8]), 1)
    with pytest.raises(p.ProtocolError, match="short"):
        p.parse_read_reply(b"\x01\x03", 1)


def test_decode_status_on_mains():
    s = p.decode_status(status_block())
    assert s.power_source == "mains" and not s.on_battery and not s.ac_lost
    assert s.battery_voltage == pytest.approx(14.48)
    assert s.output_voltage == pytest.approx(14.47)
    assert s.battery_current == pytest.approx(0.7)
    assert s.temperature == pytest.approx(33.4)
    assert s.charge_stage == pytest.approx(0.36)
    assert s.uptime == (0x008B << 16) | 0x6548
    assert s.firmware == "21900102"
    assert not s.charging  # +0.7 A at float is the known offset, not charging


def test_decode_status_on_battery_signed_current():
    s = p.decode_status(status_block({0x100A: 4, 0x100C: 0x10, 0x1011: 1340, 0x1016: 0x10000 - 550}))
    assert s.power_source == "battery" and s.on_battery and s.ac_lost
    assert s.battery_current == pytest.approx(-0.55)
    assert s.battery_power == pytest.approx(-7.37)
    assert not s.charging


def test_decode_status_charging():
    s = p.decode_status(status_block({0x1016: 6790, 0x1022: 900}))
    assert s.charging and s.charge_stage == pytest.approx(9.0)


def test_unknown_power_source_code():
    assert p.decode_status(status_block({0x100A: 7})).power_source is None


def test_decode_config():
    regs = [0] * p.CONFIG_COUNT
    regs[0x700E - p.CONFIG_BASE] = 1450
    regs[0x7011 - p.CONFIG_BASE] = 1460
    regs[0x7012 - p.CONFIG_BASE] = 600
    c = p.decode_config(regs)
    assert (c.charge_voltage, c.max_battery_voltage, c.charge_current) == (14.5, 14.6, 6.0)


def test_short_blocks_rejected():
    with pytest.raises(p.ProtocolError):
        p.decode_status([0] * 10)
    with pytest.raises(p.ProtocolError):
        p.decode_config([0] * 10)
