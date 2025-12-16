"""
BER and BLER calculation for various modulation and FEC schemes.

Modulation schemes: BPSK, QPSK, 16-QAM, 64-QAM, 256-QAM
FEC types: LDPC, Polar, Turbo (when Sionna is available)

This module provides both theoretical BER calculations (no Sionna required)
and Sionna-based simulated calculations (when GPU package is installed).
"""

import numpy as np
from typing import Optional
from enum import Enum


class ModulationScheme(str, Enum):
    """Supported modulation schemes."""

    BPSK = "bpsk"
    QPSK = "qpsk"
    QAM16 = "16qam"
    QAM64 = "64qam"
    QAM256 = "256qam"


# Mapping of modulation to bits per symbol
MODULATION_BITS = {
    "bpsk": 1,
    "qpsk": 2,
    "16qam": 4,
    "64qam": 6,
    "256qam": 8,
}


def get_bits_per_symbol(modulation: str) -> int:
    """
    Get number of bits per symbol for a modulation scheme.

    Args:
        modulation: Modulation name (e.g., 'qpsk', '64qam')

    Returns:
        Number of bits per symbol
    """
    mod_lower = modulation.lower()
    if mod_lower not in MODULATION_BITS:
        raise ValueError(f"Unknown modulation: {modulation}")
    return MODULATION_BITS[mod_lower]


class BERCalculator:
    """
    Calculate BER for various modulation schemes.

    Uses theoretical formulas for AWGN channel. For more accurate results
    with ray-traced channels, use Sionna's simulation capabilities.
    """

    def __init__(self, modulation: str):
        """
        Initialize BER calculator.

        Args:
            modulation: Modulation scheme name (e.g., 'qpsk', '64qam')
        """
        self.modulation = modulation.lower()
        self.bits_per_symbol = get_bits_per_symbol(self.modulation)

    def theoretical_ber_awgn(self, snr_db: float) -> float:
        """
        Calculate theoretical BER for uncoded system in AWGN channel.

        Uses standard formulas:
        - BPSK/QPSK: BER = Q(sqrt(2*Eb/N0)) = 0.5*erfc(sqrt(Eb/N0))
        - M-QAM: BER ≈ (4/log2(M)) * (1 - 1/sqrt(M)) * Q(sqrt(3*Eb*log2(M)/(M-1)))

        Args:
            snr_db: Signal-to-Noise Ratio in dB

        Returns:
            Bit Error Rate (0 to 0.5)
        """
        # Convert SNR to linear
        snr_linear = 10 ** (snr_db / 10)

        # Convert SNR to Eb/N0 (energy per bit to noise)
        # SNR = Eb/N0 * bits_per_symbol
        eb_n0 = snr_linear / self.bits_per_symbol

        if self.modulation in ["bpsk", "qpsk"]:
            # BER = Q(sqrt(2*Eb/N0)) = 0.5*erfc(sqrt(Eb/N0))
            # For QPSK with Gray coding, same as BPSK per bit
            ber = 0.5 * self._erfc(np.sqrt(eb_n0))
        else:
            # M-QAM approximation (valid for high SNR)
            M = 2**self.bits_per_symbol
            k = self.bits_per_symbol  # log2(M)

            # Average symbol error rate for square M-QAM
            # Using the approximation: Ps ≈ 4*(1-1/sqrt(M))*Q(sqrt(3*SNR/(M-1)))
            arg = np.sqrt(3 * snr_linear / (M - 1))
            ps = 4 * (1 - 1 / np.sqrt(M)) * self._q_function(arg)

            # Convert symbol error rate to BER (Gray coding approximation)
            # BER ≈ Ps / log2(M) for high SNR
            ber = ps / k

        # Clamp to valid range
        return float(np.clip(ber, 1e-12, 0.5))

    def ber_vs_snr(
        self, snr_db_min: float = -5.0, snr_db_max: float = 30.0, num_points: int = 50
    ) -> tuple[np.ndarray, np.ndarray]:
        """
        Calculate BER curve over SNR range.

        Args:
            snr_db_min: Minimum SNR in dB
            snr_db_max: Maximum SNR in dB
            num_points: Number of points in curve

        Returns:
            Tuple of (snr_db_array, ber_array)
        """
        snr_db = np.linspace(snr_db_min, snr_db_max, num_points)
        ber = np.array([self.theoretical_ber_awgn(s) for s in snr_db])
        return snr_db, ber

    @staticmethod
    def _q_function(x: float) -> float:
        """Q-function: Q(x) = 0.5 * erfc(x/sqrt(2))"""
        return 0.5 * np.erfc(x / np.sqrt(2))

    @staticmethod
    def _erfc(x: float) -> float:
        """Complementary error function wrapper."""
        return float(np.erfc(x))


class BLERCalculator:
    """
    Calculate BLER (Block Error Rate) for coded systems.

    This provides approximate BLER based on theoretical BER when Sionna
    is not available. For accurate BLER with specific FEC codes, use
    Sionna's encoder/decoder chains.
    """

    def __init__(
        self,
        fec_type: str,
        code_rate: float,
        modulation: str,
        block_length: int = 1024,
    ):
        """
        Initialize BLER calculator.

        Args:
            fec_type: FEC type ('ldpc', 'polar', 'turbo', 'none')
            code_rate: Code rate k/n (e.g., 0.5 for rate-1/2)
            modulation: Modulation scheme name
            block_length: Code block length in bits
        """
        self.fec_type = fec_type.lower()
        self.code_rate = code_rate
        self.modulation = modulation.lower()
        self.block_length = block_length
        self.ber_calc = BERCalculator(modulation)

        # Coding gain approximations (dB) for different FEC at code rate 0.5
        # These are rough estimates; actual gains depend on specific code design
        self.coding_gains = {
            "none": 0.0,
            "ldpc": 8.0,  # LDPC typically achieves ~1dB from capacity
            "polar": 7.5,  # Polar codes similar to LDPC with SCL decoder
            "turbo": 7.0,  # Turbo codes, good but slightly worse than LDPC
        }

    def approximate_bler(self, snr_db: float) -> float:
        """
        Approximate BLER using coding gain offset.

        This is a simplified model. For accurate BLER, use Sionna simulations.

        The model applies a coding gain to shift the BER curve, then
        estimates BLER based on block length.

        Args:
            snr_db: Signal-to-Noise Ratio in dB

        Returns:
            Approximate Block Error Rate (0 to 1)
        """
        if self.fec_type == "none":
            # No coding - use BER-based block error
            ber = self.ber_calc.theoretical_ber_awgn(snr_db)
            # BLER = 1 - (1-BER)^block_length
            if ber < 1e-10:
                bler = self.block_length * ber  # Approximation for small BER
            else:
                bler = 1.0 - (1.0 - ber) ** self.block_length
            return float(np.clip(bler, 1e-12, 1.0))

        # Apply coding gain
        coding_gain = self.coding_gains.get(self.fec_type, 0.0)

        # Adjust coding gain based on code rate
        # Higher rate codes have less redundancy, lower gain
        rate_factor = 1.0 - 0.5 * (self.code_rate - 0.5)  # Normalized around rate-0.5
        effective_gain = coding_gain * rate_factor

        # Calculate equivalent uncoded SNR
        effective_snr = snr_db + effective_gain

        # Get BER at effective SNR
        ber = self.ber_calc.theoretical_ber_awgn(effective_snr)

        # Information bits per block
        info_bits = int(self.block_length * self.code_rate)

        # BLER approximation: probability of at least one bit error in info bits
        if ber < 1e-10:
            bler = info_bits * ber
        else:
            bler = 1.0 - (1.0 - ber) ** info_bits

        return float(np.clip(bler, 1e-12, 1.0))

    def bler_vs_snr(
        self, snr_db_min: float = -5.0, snr_db_max: float = 30.0, num_points: int = 50
    ) -> tuple[np.ndarray, np.ndarray]:
        """
        Calculate BLER curve over SNR range.

        Args:
            snr_db_min: Minimum SNR in dB
            snr_db_max: Maximum SNR in dB
            num_points: Number of points in curve

        Returns:
            Tuple of (snr_db_array, bler_array)
        """
        snr_db = np.linspace(snr_db_min, snr_db_max, num_points)
        bler = np.array([self.approximate_bler(s) for s in snr_db])
        return snr_db, bler


# Optional Sionna-based calculators (only available with GPU package)
_sionna_available = False
try:
    import tensorflow as tf
    from sionna.phy.mapping import Constellation, Mapper, Demapper

    _sionna_available = True
except ImportError:
    pass


def is_sionna_available() -> bool:
    """Check if Sionna is available for advanced simulations."""
    return _sionna_available


class SionnaBERCalculator:
    """
    BER calculator using Sionna's modulation/demodulation chain.

    Requires the 'gpu' optional dependencies to be installed.
    """

    def __init__(self, modulation: str):
        """
        Initialize Sionna-based BER calculator.

        Args:
            modulation: Modulation scheme name

        Raises:
            ImportError: If Sionna is not installed
        """
        if not _sionna_available:
            raise ImportError(
                "Sionna is required for SionnaBERCalculator. "
                "Install with: pip install sine[gpu]"
            )

        self.modulation = modulation.lower()
        self.bits_per_symbol = get_bits_per_symbol(self.modulation)

        # Create Sionna constellation
        self.constellation = Constellation(
            constellation_type="qam", num_bits_per_symbol=self.bits_per_symbol
        )
        self.mapper = Mapper(constellation=self.constellation)
        self.demapper = Demapper(
            demapping_method="app", constellation=self.constellation
        )

    def simulate_ber(self, snr_db: float, num_bits: int = 100000) -> float:
        """
        Simulate BER using Sionna's modulation chain.

        Args:
            snr_db: Signal-to-Noise Ratio in dB
            num_bits: Number of bits to simulate

        Returns:
            Simulated Bit Error Rate
        """
        import tensorflow as tf

        # Ensure num_bits is divisible by bits_per_symbol
        num_bits = (num_bits // self.bits_per_symbol) * self.bits_per_symbol

        # Generate random bits
        bits = tf.random.uniform([1, num_bits], 0, 2, dtype=tf.int32)
        bits = tf.cast(bits, tf.float32)

        # Map to symbols
        symbols = self.mapper(bits)

        # Add AWGN noise
        snr_linear = 10 ** (snr_db / 10)
        noise_var = 1.0 / snr_linear
        noise = tf.complex(
            tf.random.normal(tf.shape(symbols)) * tf.sqrt(noise_var / 2),
            tf.random.normal(tf.shape(symbols)) * tf.sqrt(noise_var / 2),
        )
        received = symbols + noise

        # Demap to LLRs
        llrs = self.demapper([received, noise_var])

        # Hard decision
        decoded_bits = tf.cast(llrs < 0, tf.float32)

        # Compute BER
        errors = tf.reduce_sum(tf.abs(bits - decoded_bits))
        ber = errors / num_bits

        return float(ber.numpy())
