"""
Packet Error Rate (PER) calculation from BER or BLER.

For uncoded systems:
    PER = 1 - (1 - BER)^packet_bits

For coded systems:
    PER = BLER (directly use block error rate)

This assumes one transport block per packet. For multiple code blocks
per packet, use:
    PER = 1 - (1 - BLER)^num_code_blocks
"""

import numpy as np
from dataclasses import dataclass
from typing import Optional


@dataclass
class ChannelMetrics:
    """Complete channel quality metrics."""

    path_loss_db: float
    received_power_dbm: float
    snr_db: float
    ber: float
    bler: Optional[float]
    per: float

    # Derived netem parameters
    delay_ms: float
    jitter_ms: float
    loss_percent: float
    rate_mbps: float


class PERCalculator:
    """Calculate Packet Error Rate from BER or BLER."""

    # Default packet size (Ethernet MTU)
    DEFAULT_PACKET_BYTES = 1500
    DEFAULT_PACKET_BITS = DEFAULT_PACKET_BYTES * 8  # 12000 bits

    def __init__(self, fec_type: str = "none"):
        """
        Initialize PER calculator.

        Args:
            fec_type: FEC type ('none', 'ldpc', 'polar', 'turbo')
        """
        self.fec_type = fec_type.lower()
        self.is_coded = self.fec_type not in ["none", "uncoded"]

    def calculate_per(
        self,
        ber: Optional[float] = None,
        bler: Optional[float] = None,
        packet_bits: int = DEFAULT_PACKET_BITS,
        num_code_blocks: int = 1,
    ) -> float:
        """
        Calculate PER based on BER or BLER.

        Args:
            ber: Bit error rate (for uncoded systems)
            bler: Block error rate (for coded systems)
            packet_bits: Number of bits per packet (default: 12000 for 1500 byte MTU)
            num_code_blocks: Number of FEC code blocks per packet

        Returns:
            Packet error rate (0 to 1)
        """
        if self.is_coded:
            if bler is None:
                raise ValueError("BLER required for coded systems")
            # For coded systems, use BLER directly
            # If multiple code blocks per packet:
            # PER = 1 - (1 - BLER)^num_code_blocks
            if num_code_blocks == 1:
                per = bler
            else:
                per = 1.0 - (1.0 - bler) ** num_code_blocks
        else:
            if ber is None:
                raise ValueError("BER required for uncoded systems")
            # For uncoded: PER = 1 - (1 - BER)^packet_bits
            # Use log for numerical stability with small BER
            if ber < 1e-12:
                per = packet_bits * ber  # Linear approximation for small BER
            elif ber > 0.5:
                per = 1.0  # Essentially random
            else:
                per = 1.0 - (1.0 - ber) ** packet_bits

        return float(np.clip(per, 0.0, 1.0))

    @staticmethod
    def per_to_netem_loss(per: float) -> float:
        """
        Convert PER to netem loss percentage.

        Args:
            per: Packet error rate (0 to 1)

        Returns:
            Loss percentage for netem (0 to 100)
        """
        return per * 100.0

    @staticmethod
    def calculate_effective_rate(
        bandwidth_mhz: float,
        modulation_bits: int,
        code_rate: float = 1.0,
        per: float = 0.0,
    ) -> float:
        """
        Calculate effective data rate considering modulation, coding, and PER.

        This is a simplified calculation. Actual WiFi rates depend on
        many factors including OFDM parameters, guard intervals, etc.

        Args:
            bandwidth_mhz: Channel bandwidth in MHz
            modulation_bits: Bits per symbol for the modulation scheme
            code_rate: FEC code rate (1.0 for uncoded)
            per: Packet error rate (for throughput reduction)

        Returns:
            Effective data rate in Mbps
        """
        # Simplified rate calculation
        # Assumes ~80% efficiency for OFDM overhead, guard intervals, etc.
        ofdm_efficiency = 0.8

        # Raw bit rate = bandwidth * bits_per_symbol * efficiency
        raw_rate_mbps = bandwidth_mhz * modulation_bits * ofdm_efficiency

        # Apply code rate
        coded_rate_mbps = raw_rate_mbps * code_rate

        # Apply PER (reduces effective throughput)
        effective_rate_mbps = coded_rate_mbps * (1.0 - per)

        return float(max(0.1, effective_rate_mbps))  # Minimum 0.1 Mbps

    def calculate_netem_params(
        self,
        path_loss_db: float,
        received_power_dbm: float,
        snr_db: float,
        ber: float,
        bler: Optional[float],
        delay_ns: float,
        delay_spread_ns: float,
        bandwidth_mhz: float,
        modulation_bits: int,
        code_rate: float = 1.0,
        packet_bits: int = DEFAULT_PACKET_BITS,
    ) -> ChannelMetrics:
        """
        Calculate complete channel metrics including netem parameters.

        Args:
            path_loss_db: Path loss from ray tracing
            received_power_dbm: Received signal power
            snr_db: Signal-to-noise ratio
            ber: Bit error rate
            bler: Block error rate (None for uncoded)
            delay_ns: Minimum propagation delay in nanoseconds
            delay_spread_ns: Delay spread (for jitter) in nanoseconds
            bandwidth_mhz: Channel bandwidth in MHz
            modulation_bits: Bits per symbol
            code_rate: FEC code rate
            packet_bits: Bits per packet

        Returns:
            ChannelMetrics with all computed values
        """
        # Calculate PER
        per = self.calculate_per(
            ber=ber if not self.is_coded else None,
            bler=bler if self.is_coded else None,
            packet_bits=packet_bits,
        )

        # Convert delays to milliseconds
        delay_ms = delay_ns / 1e6
        jitter_ms = delay_spread_ns / 1e6

        # Calculate effective rate
        rate_mbps = self.calculate_effective_rate(
            bandwidth_mhz=bandwidth_mhz,
            modulation_bits=modulation_bits,
            code_rate=code_rate,
            per=per,
        )

        # Convert PER to loss percentage
        loss_percent = self.per_to_netem_loss(per)

        return ChannelMetrics(
            path_loss_db=path_loss_db,
            received_power_dbm=received_power_dbm,
            snr_db=snr_db,
            ber=ber,
            bler=bler,
            per=per,
            delay_ms=delay_ms,
            jitter_ms=jitter_ms,
            loss_percent=loss_percent,
            rate_mbps=rate_mbps,
        )
