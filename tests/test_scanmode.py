import pytest

from conftest import load

s = load("scanmode")


@pytest.mark.parametrize(
    "options,expected",
    [
        ({}, "auto"),  # HA default
        ({"mode": "auto"}, "auto"),
        ({"mode": "active"}, "active"),
        ({"mode": "passive"}, "passive"),
        ({"passive": True}, "passive"),  # legacy option only
        ({"passive": False}, "active"),
        ({"mode": "active", "passive": True}, "active"),  # new option wins
        ({"mode": "bogus", "passive": True}, "passive"),
        ({"mode": "bogus"}, "auto"),
    ],
)
def test_scanning_mode(options, expected):
    assert s.scanning_mode(options) == expected
