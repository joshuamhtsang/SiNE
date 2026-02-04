"""Tests for antenna configuration schema validation."""

import pytest
from pydantic import ValidationError
from sine.config.schema import WirelessParams, Position, AntennaPattern


def test_antenna_both_specified_raises_error():
    """Test that specifying both antenna_pattern and antenna_gain_dbi raises error."""
    with pytest.raises(ValueError, match="Cannot specify both"):
        WirelessParams(
            position=Position(x=0, y=0, z=1),
            antenna_pattern=AntennaPattern.ISO,
            antenna_gain_dbi=2.0,
            mcs_table="examples/common_data/wifi6_mcs.csv"
        )


def test_antenna_neither_specified_raises_error():
    """Test that specifying neither antenna_pattern nor antenna_gain_dbi raises error."""
    with pytest.raises(ValueError, match="requires exactly one"):
        WirelessParams(
            position=Position(x=0, y=0, z=1),
            mcs_table="examples/common_data/wifi6_mcs.csv"
        )


def test_antenna_pattern_only_valid():
    """Test that antenna_pattern alone is valid."""
    params = WirelessParams(
        position=Position(x=0, y=0, z=1),
        antenna_pattern=AntennaPattern.HW_DIPOLE,
        mcs_table="examples/common_data/wifi6_mcs.csv"
    )
    assert params.antenna_pattern == AntennaPattern.HW_DIPOLE
    assert params.antenna_gain_dbi is None


def test_antenna_gain_only_valid():
    """Test that antenna_gain_dbi alone is valid."""
    params = WirelessParams(
        position=Position(x=0, y=0, z=1),
        antenna_gain_dbi=3.0,
        mcs_table="examples/common_data/wifi6_mcs.csv"
    )
    assert params.antenna_gain_dbi == 3.0
    assert params.antenna_pattern is None


def test_antenna_gain_range_validation():
    """Test that antenna_gain_dbi respects ge/le constraints."""
    # Too low
    with pytest.raises(ValidationError, match="greater than or equal to -10"):
        WirelessParams(
            position=Position(x=0, y=0, z=1),
            antenna_gain_dbi=-15.0,
            mcs_table="examples/common_data/wifi6_mcs.csv"
        )

    # Too high
    with pytest.raises(ValidationError, match="less than or equal to 30"):
        WirelessParams(
            position=Position(x=0, y=0, z=1),
            antenna_gain_dbi=35.0,
            mcs_table="examples/common_data/wifi6_mcs.csv"
        )


def test_antenna_pattern_all_types_valid():
    """Test that all antenna pattern types are valid."""
    for pattern in [AntennaPattern.ISO, AntennaPattern.DIPOLE, AntennaPattern.HW_DIPOLE, AntennaPattern.TR38901]:
        params = WirelessParams(
            position=Position(x=0, y=0, z=1),
            antenna_pattern=pattern,
            mcs_table="examples/common_data/wifi6_mcs.csv"
        )
        assert params.antenna_pattern == pattern
        assert params.antenna_gain_dbi is None


def test_antenna_gain_boundary_values():
    """Test antenna_gain_dbi at boundary values."""
    # Minimum valid
    params_min = WirelessParams(
        position=Position(x=0, y=0, z=1),
        antenna_gain_dbi=-10.0,
        mcs_table="examples/common_data/wifi6_mcs.csv"
    )
    assert params_min.antenna_gain_dbi == -10.0

    # Maximum valid
    params_max = WirelessParams(
        position=Position(x=0, y=0, z=1),
        antenna_gain_dbi=30.0,
        mcs_table="examples/common_data/wifi6_mcs.csv"
    )
    assert params_max.antenna_gain_dbi == 30.0

    # Typical values
    for gain in [0.0, 2.15, 3.0, 8.0]:
        params = WirelessParams(
            position=Position(x=0, y=0, z=1),
            antenna_gain_dbi=gain,
            mcs_table="examples/common_data/wifi6_mcs.csv"
        )
        assert params.antenna_gain_dbi == gain
