import pytest

from conftest import load

b = load("battery")


def test_lifepo4_with_bms_defaults():
    p = b.profile_from_options({"battery_type": "lifepo4", "battery_capacity_ah": 30, "battery_bms": True})
    assert (p.rated_voltage, p.usable_pct) == (12.8, 90)
    assert p.rated_wh == pytest.approx(384)
    assert p.usable_wh == pytest.approx(345.6)


def test_lifepo4_without_bms_is_more_conservative():
    p = b.profile_from_options({"battery_type": "lifepo4", "battery_capacity_ah": 30, "battery_bms": False})
    assert p.usable_pct == 80 and p.usable_wh == pytest.approx(307.2)


@pytest.mark.parametrize("btype", ["agm", "gel", "lead_acid"])
def test_lead_acid_defaults(btype):
    p = b.profile_from_options({"battery_type": btype, "battery_capacity_ah": 40})
    assert (p.rated_voltage, p.usable_pct) == (12.0, 70)
    assert p.usable_wh == pytest.approx(336)


def test_explicit_values_override_defaults():
    p = b.profile_from_options({"battery_type": "lifepo4", "battery_capacity_ah": 100,
                                "battery_voltage": 12.8, "battery_usable_pct": 75, "battery_bms": True})
    assert p.usable_wh == pytest.approx(960)


def test_no_capacity_means_no_profile():
    assert b.profile_from_options({}) is None
    assert b.profile_from_options({"battery_type": "agm", "battery_capacity_ah": 0}) is None


def test_legacy_usable_wh_option_still_works():
    p = b.profile_from_options({"battery_usable_wh": 346})
    assert p.usable_wh == pytest.approx(346)


def test_new_options_win_over_legacy():
    p = b.profile_from_options({"battery_usable_wh": 999, "battery_type": "agm", "battery_capacity_ah": 10})
    assert p.usable_wh == pytest.approx(84)
