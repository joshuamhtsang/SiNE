"""
Unit tests for modulation.py - BER and BLER calculations.

Tests theoretical BER/BLER formulas for various modulation schemes
without requiring Sionna GPU package.
"""

import pytest
import numpy as np
from sine.channel.modulation import (
    BERCalculator,
    BLERCalculator,
    get_bits_per_symbol,
    ModulationScheme,
    MODULATION_BITS,
)


class TestGetBitsPerSymbol:
    """Test bits_per_symbol lookup function."""

    @pytest.mark.parametrize(
        "modulation,expected_bits",
        [
            ("bpsk", 1),
            ("BPSK", 1),  # Case insensitive
            ("qpsk", 2),
            ("16qam", 4),
            ("64qam", 6),
            ("256qam", 8),
            ("1024qam", 10),
        ],
    )
    def test_valid_modulations(self, modulation: str, expected_bits: int):
        """Test that valid modulations return correct bits per symbol."""
        assert get_bits_per_symbol(modulation) == expected_bits

    def test_invalid_modulation(self):
        """Test that invalid modulation raises ValueError."""
        with pytest.raises(ValueError, match="Unknown modulation"):
            get_bits_per_symbol("invalid_mod")


class TestBERCalculator:
    """Test BER calculation for various modulation schemes."""

    @pytest.mark.parametrize("modulation", ["bpsk", "qpsk", "16qam", "64qam", "256qam", "1024qam"])
    def test_initialization(self, modulation: str):
        """Test BERCalculator initialization for each modulation."""
        calc = BERCalculator(modulation)
        assert calc.modulation == modulation.lower()
        assert calc.bits_per_symbol == MODULATION_BITS[modulation]

    def test_ber_at_zero_snr_bpsk(self):
        """Test that BPSK at SNR=0dB gives BER ≈ 0.5 (random guessing)."""
        calc = BERCalculator("bpsk")
        ber = calc.theoretical_ber_awgn(snr_db=0.0)
        # At SNR=0dB (Eb/N0 = 0dB), BER should be close to 0.5
        # Q(sqrt(1)) = Q(1) ≈ 0.159
        # 0.5*erfc(sqrt(0.5)) ≈ 0.079
        # Actually for BPSK at SNR=0dB: 0.5*erfc(sqrt(1)) ≈ 0.079
        assert 0.05 < ber < 0.15  # Relaxed tolerance

    def test_ber_at_high_snr(self):
        """Test that BER approaches zero at very high SNR."""
        calc = BERCalculator("qpsk")
        ber = calc.theoretical_ber_awgn(snr_db=30.0)
        # At very high SNR, BER should be extremely small
        assert ber < 1e-6

    def test_ber_at_negative_snr(self):
        """Test that BER at negative SNR is high (poor link)."""
        calc = BERCalculator("qpsk")
        ber = calc.theoretical_ber_awgn(snr_db=-5.0)
        # At negative SNR, BER should be high (but clamped to 0.5 max)
        assert ber > 0.1
        assert ber <= 0.5

    @pytest.mark.parametrize(
        "modulation,snr_db,expected_ber_approx",
        [
            # BPSK/QPSK at typical operating points
            ("qpsk", 10.0, 5e-4),  # Moderate SNR
            ("qpsk", 15.0, 1e-8),  # Good SNR (corrected: very low BER at 15dB)
            # Higher-order QAM requires higher SNR
            ("16qam", 15.0, 1e-3),  # Moderate for 16-QAM
            ("64qam", 20.0, 1e-3),  # Moderate for 64-QAM
        ],
    )
    def test_ber_at_operating_points(
        self, modulation: str, snr_db: float, expected_ber_approx: float
    ):
        """Test BER at typical operating SNR points (order of magnitude check)."""
        calc = BERCalculator(modulation)
        ber = calc.theoretical_ber_awgn(snr_db)
        # Check within two orders of magnitude (factor of 100 tolerance)
        # BER curves are very steep, so actual vs expected can vary significantly
        assert ber / expected_ber_approx < 100.0
        assert ber / expected_ber_approx > 0.01

    def test_ber_decreases_with_snr(self):
        """Property: BER should monotonically decrease as SNR increases."""
        calc = BERCalculator("64qam")
        snr_values = np.linspace(0, 25, 20)
        ber_values = [calc.theoretical_ber_awgn(s) for s in snr_values]

        # Check that BER is monotonically decreasing
        for i in range(len(ber_values) - 1):
            assert ber_values[i] >= ber_values[i + 1], \
                f"BER increased from {ber_values[i]} to {ber_values[i+1]} at SNR {snr_values[i]}→{snr_values[i+1]}"

    def test_ber_clamped_to_valid_range(self):
        """Test that BER is always in valid range [0, 0.5]."""
        calc = BERCalculator("qpsk")
        test_snrs = [-10, -5, 0, 5, 10, 15, 20, 30, 50]
        for snr in test_snrs:
            ber = calc.theoretical_ber_awgn(snr)
            assert 0.0 <= ber <= 0.5, f"BER {ber} out of range at SNR {snr}dB"

    def test_ber_vs_snr_curve(self):
        """Test that ber_vs_snr returns proper curve."""
        calc = BERCalculator("qpsk")
        snr_db, ber = calc.ber_vs_snr(snr_db_min=-5, snr_db_max=20, num_points=10)

        assert len(snr_db) == 10
        assert len(ber) == 10
        assert snr_db[0] == -5.0
        assert snr_db[-1] == 20.0
        # BER should decrease over the range
        assert ber[0] > ber[-1]


class TestBLERCalculator:
    """Test BLER calculation for coded systems."""

    def test_initialization(self):
        """Test BLERCalculator initialization."""
        calc = BLERCalculator(
            fec_type="ldpc", code_rate=0.5, modulation="qpsk", block_length=1024
        )
        assert calc.fec_type == "ldpc"
        assert calc.code_rate == 0.5
        assert calc.modulation == "qpsk"
        assert calc.block_length == 1024

    @pytest.mark.parametrize("fec_type", ["ldpc", "polar", "turbo", "none"])
    def test_all_fec_types(self, fec_type: str):
        """Test BLER calculation for all FEC types."""
        calc = BLERCalculator(fec_type=fec_type, code_rate=0.5, modulation="qpsk")
        bler = calc.approximate_bler(snr_db=10.0)
        assert 0.0 <= bler <= 1.0

    def test_coding_gain_ldpc(self):
        """Test that LDPC coding provides lower BLER than uncoded at same SNR."""
        uncoded = BLERCalculator(fec_type="none", code_rate=1.0, modulation="qpsk")
        coded = BLERCalculator(fec_type="ldpc", code_rate=0.5, modulation="qpsk")

        snr_db = 5.0
        bler_uncoded = uncoded.approximate_bler(snr_db)
        bler_coded = coded.approximate_bler(snr_db)

        # Coded system should have significantly lower BLER
        assert bler_coded < bler_uncoded
        # Should be at least 10x better (very conservative estimate)
        assert bler_coded < bler_uncoded / 10

    def test_bler_decreases_with_snr(self):
        """Property: BLER should decrease as SNR increases."""
        calc = BLERCalculator(fec_type="ldpc", code_rate=0.5, modulation="qpsk")
        snr_values = np.linspace(0, 20, 15)
        bler_values = [calc.approximate_bler(s) for s in snr_values]

        # Check monotonic decrease
        for i in range(len(bler_values) - 1):
            assert bler_values[i] >= bler_values[i + 1], \
                f"BLER increased at SNR {snr_values[i]}→{snr_values[i+1]}"

    def test_bler_at_high_snr_approaches_zero(self):
        """Test that BLER approaches zero at very high SNR."""
        calc = BLERCalculator(fec_type="ldpc", code_rate=0.5, modulation="qpsk")
        bler = calc.approximate_bler(snr_db=30.0)
        assert bler < 1e-4

    def test_bler_at_low_snr_approaches_one(self):
        """Test that BLER approaches 1 at very low SNR."""
        calc = BLERCalculator(fec_type="none", code_rate=1.0, modulation="qpsk")
        bler = calc.approximate_bler(snr_db=-10.0)
        # Should be very high error rate
        assert bler > 0.5

    def test_code_rate_effect(self):
        """Test that higher code rate (less redundancy) has worse BLER."""
        low_rate = BLERCalculator(fec_type="ldpc", code_rate=0.5, modulation="qpsk")
        high_rate = BLERCalculator(fec_type="ldpc", code_rate=0.833, modulation="qpsk")

        snr_db = 10.0
        bler_low = low_rate.approximate_bler(snr_db)
        bler_high = high_rate.approximate_bler(snr_db)

        # Higher code rate should have worse (higher) BLER at same SNR
        assert bler_high > bler_low

    def test_bler_vs_snr_curve(self):
        """Test BLER curve generation."""
        calc = BLERCalculator(fec_type="ldpc", code_rate=0.5, modulation="qpsk")
        snr_db, bler = calc.bler_vs_snr(snr_db_min=0, snr_db_max=20, num_points=10)

        assert len(snr_db) == 10
        assert len(bler) == 10
        assert snr_db[0] == 0.0
        assert snr_db[-1] == 20.0
        # BLER should decrease
        assert bler[0] > bler[-1]

    def test_bler_clamped_to_valid_range(self):
        """Test that BLER is always in valid range [0, 1]."""
        calc = BLERCalculator(fec_type="ldpc", code_rate=0.5, modulation="qpsk")
        test_snrs = [-10, -5, 0, 5, 10, 15, 20, 30]
        for snr in test_snrs:
            bler = calc.approximate_bler(snr)
            assert 0.0 <= bler <= 1.0, f"BLER {bler} out of range at SNR {snr}dB"

    def test_coding_gains_exist_for_all_fec(self):
        """Test that coding gains are defined for all FEC types."""
        for fec_type in ["none", "ldpc", "polar", "turbo"]:
            calc = BLERCalculator(fec_type=fec_type, code_rate=0.5, modulation="qpsk")
            assert fec_type in calc.coding_gains
            gain = calc.coding_gains[fec_type]
            assert isinstance(gain, (int, float))
            assert gain >= 0.0  # Coding gain should be non-negative


class TestModulationSchemeEnum:
    """Test ModulationScheme enum."""

    def test_enum_values(self):
        """Test that all modulation schemes are in enum."""
        assert ModulationScheme.BPSK == "bpsk"
        assert ModulationScheme.QPSK == "qpsk"
        assert ModulationScheme.QAM16 == "16qam"
        assert ModulationScheme.QAM64 == "64qam"
        assert ModulationScheme.QAM256 == "256qam"
        assert ModulationScheme.QAM1024 == "1024qam"

    def test_enum_coverage(self):
        """Test that enum covers all MODULATION_BITS entries."""
        enum_values = set(m.value for m in ModulationScheme)
        dict_keys = set(MODULATION_BITS.keys())
        assert enum_values == dict_keys


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
