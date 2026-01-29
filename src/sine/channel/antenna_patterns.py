"""
Antenna pattern gain mappings for SiNE.

These values represent the actual antenna gains (in dBi) provided by Sionna RT's
built-in antenna patterns. The gains are embedded in the path coefficients computed
by Sionna's ray tracing engine.

References:
- Sionna RT Antenna Patterns: https://nvlabs.github.io/sionna/api/rt.html#antenna-patterns
- Gain computation method: PlanarArray.antenna_pattern.compute_gain()
- Technical details: Sionna RT Technical Report, Section 3.3 (Channel Coefficients)

Values were measured using:
    from sionna.rt import PlanarArray
    array = PlanarArray(num_rows=1, num_cols=1, pattern="<pattern>", polarization="V")
    directivity, gain, efficiency = array.antenna_pattern.compute_gain()

Note: These gains are automatically included in Sionna's path loss calculations.
Do NOT add them again in link budget calculations when using ray tracing.
"""

from typing import Final

# Antenna pattern gain mapping (pattern name -> gain in dBi)
# Values measured from Sionna RT v1.2.1
ANTENNA_PATTERN_GAINS: Final[dict[str, float]] = {
    # Isotropic antenna (reference, 0 dBi by definition)
    # https://nvlabs.github.io/sionna/api/rt.html#sionna.rt.antenna_pattern.v_iso_pattern
    "iso": 0.0,
    # Short dipole (Balanis, Eq. 4-26a)
    # https://nvlabs.github.io/sionna/api/rt.html#sionna.rt.antenna_pattern.v_dipole_pattern
    # Measured: directivity=1.76 dB, gain=1.76 dB, efficiency=100%
    "dipole": 1.76,
    # Half-wavelength dipole (Balanis, Eq. 4-84)
    # https://nvlabs.github.io/sionna/api/rt.html#sionna.rt.antenna_pattern.v_hw_dipole_pattern
    # Measured: directivity=2.15 dB, gain=2.16 dB, efficiency=100%
    "hw_dipole": 2.16,
    # 3GPP TR 38.901 directional antenna (Table 7.3-1)
    # https://nvlabs.github.io/sionna/api/rt.html#sionna.rt.antenna_pattern.v_tr38901_pattern
    # Measured: directivity=9.83 dB, gain=8.0 dB, efficiency=65.7%
    "tr38901": 8.0,
}


def get_antenna_gain(antenna_pattern: str) -> float:
    """
    Get the antenna gain in dBi for a given antenna pattern.

    This function returns the measured gain values from Sionna RT's antenna patterns.
    These gains are already embedded in Sionna's path coefficients when using ray tracing.

    Args:
        antenna_pattern: Antenna pattern name ("iso", "dipole", "hw_dipole", "tr38901")

    Returns:
        Antenna gain in dBi

    Raises:
        ValueError: If antenna_pattern is not recognized

    Example:
        >>> get_antenna_gain("dipole")
        1.76
        >>> get_antenna_gain("iso")
        0.0
    """
    if antenna_pattern not in ANTENNA_PATTERN_GAINS:
        valid_patterns = ", ".join(ANTENNA_PATTERN_GAINS.keys())
        raise ValueError(
            f"Unknown antenna pattern: '{antenna_pattern}'. "
            f"Valid patterns: {valid_patterns}"
        )
    return ANTENNA_PATTERN_GAINS[antenna_pattern]


def get_link_antenna_gain(
    tx_pattern: str | None = None,
    rx_pattern: str | None = None,
    tx_gain_dbi: float | None = None,
    rx_gain_dbi: float | None = None,
) -> tuple[float, float]:
    """
    Get TX and RX antenna gains from either pattern names or explicit gain values.

    This function supports both antenna pattern-based gains (for Sionna RT) and
    explicit gain values (for FSPL fallback mode).

    Args:
        tx_pattern: TX antenna pattern name (optional)
        rx_pattern: RX antenna pattern name (optional)
        tx_gain_dbi: TX antenna gain in dBi (optional)
        rx_gain_dbi: RX antenna gain in dBi (optional)

    Returns:
        Tuple of (tx_gain_dbi, rx_gain_dbi)

    Raises:
        ValueError: If neither pattern nor explicit gain is provided for TX or RX

    Example:
        >>> get_link_antenna_gain(tx_pattern="dipole", rx_pattern="dipole")
        (1.76, 1.76)
        >>> get_link_antenna_gain(tx_gain_dbi=3.0, rx_gain_dbi=3.0)
        (3.0, 3.0)
    """
    # Get TX gain
    if tx_pattern is not None:
        tx_gain = get_antenna_gain(tx_pattern)
    elif tx_gain_dbi is not None:
        tx_gain = tx_gain_dbi
    else:
        raise ValueError("Must specify either tx_pattern or tx_gain_dbi")
    # Get RX gain
    if rx_pattern is not None:
        rx_gain = get_antenna_gain(rx_pattern)
    elif rx_gain_dbi is not None:
        rx_gain = rx_gain_dbi
    else:
        raise ValueError("Must specify either rx_pattern or rx_gain_dbi")
    return tx_gain, rx_gain
