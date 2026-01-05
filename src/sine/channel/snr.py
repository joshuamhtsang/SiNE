"""
SNR (Signal-to-Noise Ratio) calculation from link budget.

SNR (dB) = P_rx (dBm) - N (dBm)

CRITICAL - Antenna Gain Handling:
When using Sionna ray tracing, the path coefficients from paths.cir() ALREADY
include antenna pattern gains from both TX and RX antennas. Therefore:

  P_rx = P_tx - channel_loss_db  (Sionna RT - DEFAULT)

Do NOT add antenna gains again, as this causes double-counting and ~6-12 dB
SNR overestimation.

For fallback calculations using FSPL or other models without antenna effects:

  P_rx = P_tx + G_tx - L_path + G_rx  (FSPL fallback only)

Noise floor:
  N = kTB = -174 dBm/Hz + 10*log10(B) + NF (thermal noise)

For WiFi6 at 80MHz bandwidth with 7dB noise figure:
  N = -174 + 10*log10(80e6) + 7 = -174 + 79 + 7 = -88 dBm
"""

import numpy as np

# Physical constants
BOLTZMANN_DBM_HZ = -174.0  # Thermal noise floor in dBm/Hz at 290K (room temp)
SPEED_OF_LIGHT = 3e8  # m/s


class SNRCalculator:
    """Calculate SNR from link budget parameters."""

    def __init__(
        self,
        bandwidth_hz: float,
        temperature_k: float = 290.0,
        noise_figure_db: float = 7.0,
    ):
        """
        Initialize SNR calculator.

        Args:
            bandwidth_hz: Channel bandwidth in Hz
            temperature_k: Temperature in Kelvin (default 290K = 17°C)
            noise_figure_db: Receiver noise figure in dB
                Typical values:
                - WiFi receivers (consumer): 6-8 dB
                - Cellular base stations: 3-5 dB
                - High-performance SDRs: 2-4 dB
                - Low-cost IoT radios: 8-12 dB
        """
        self.bandwidth_hz = bandwidth_hz
        self.temperature_k = temperature_k
        self.noise_figure_db = noise_figure_db

        # Calculate noise floor
        # N = -174 dBm/Hz + 10*log10(B) + NF
        self.noise_floor_dbm = (
            BOLTZMANN_DBM_HZ + 10 * np.log10(bandwidth_hz) + noise_figure_db
        )

    def calculate_received_power(
        self,
        tx_power_dbm: float,
        tx_gain_dbi: float,
        rx_gain_dbi: float,
        path_loss_db: float,
        from_sionna: bool = True,
    ) -> float:
        """
        Calculate received power using link budget.

        CRITICAL: Antenna gain handling depends on path loss source:
        - from_sionna=True (default): Path loss from Sionna RT already includes
          antenna pattern gains. Do NOT add gains again.
          Formula: P_rx = P_tx - channel_loss_db
        - from_sionna=False: Path loss from FSPL or other model without antenna
          effects. Add gains explicitly.
          Formula: P_rx = P_tx + G_tx - L_path + G_rx

        Args:
            tx_power_dbm: Transmit power in dBm
            tx_gain_dbi: Transmit antenna gain in dBi (NOT used if from_sionna=True)
            rx_gain_dbi: Receive antenna gain in dBi (NOT used if from_sionna=True)
            path_loss_db: Path loss in dB (positive value)
            from_sionna: If True, path_loss_db from Sionna RT (includes antenna gains).
                        If False, path_loss_db is pure propagation loss (e.g., FSPL).

        Returns:
            Received power in dBm
        """
        if from_sionna:
            # Sionna path coefficients already include antenna patterns
            # path_loss_db is actually "channel_loss_db" (includes antenna effects)
            return tx_power_dbm - path_loss_db
        else:
            # Classic link budget for FSPL or other models without antenna effects
            return tx_power_dbm + tx_gain_dbi - path_loss_db + rx_gain_dbi

    def calculate_snr(self, received_power_dbm: float) -> float:
        """
        Calculate SNR from received power.

        SNR (dB) = P_rx (dBm) - N (dBm)

        Args:
            received_power_dbm: Received signal power in dBm

        Returns:
            SNR in dB
        """
        return received_power_dbm - self.noise_floor_dbm

    def calculate_link_snr(
        self,
        tx_power_dbm: float,
        tx_gain_dbi: float,
        rx_gain_dbi: float,
        path_loss_db: float,
        from_sionna: bool = True,
    ) -> tuple[float, float]:
        """
        Full SNR calculation for a wireless link.

        Args:
            tx_power_dbm: Transmit power in dBm
            tx_gain_dbi: Transmit antenna gain in dBi (ignored if from_sionna=True)
            rx_gain_dbi: Receive antenna gain in dBi (ignored if from_sionna=True)
            path_loss_db: Path loss in dB
            from_sionna: If True (default), path_loss_db from Sionna RT (includes
                        antenna gains). If False, path_loss_db is pure propagation loss.

        Returns:
            Tuple of (received_power_dbm, snr_db)
        """
        rx_power = self.calculate_received_power(
            tx_power_dbm, tx_gain_dbi, rx_gain_dbi, path_loss_db, from_sionna
        )
        snr = self.calculate_snr(rx_power)
        return rx_power, snr

    @staticmethod
    def free_space_path_loss(distance_m: float, frequency_hz: float) -> float:
        """
        Calculate free-space path loss (FSPL) for comparison/fallback.

        FSPL (dB) = 20*log10(d) + 20*log10(f) + 20*log10(4*pi/c)
                  = 20*log10(d) + 20*log10(f) - 147.55

        Args:
            distance_m: Distance in meters
            frequency_hz: Frequency in Hz

        Returns:
            Free-space path loss in dB
        """
        if distance_m <= 0:
            return 0.0
        fspl = 20 * np.log10(distance_m) + 20 * np.log10(frequency_hz) - 147.55
        return float(fspl)

    @staticmethod
    def distance_from_positions(
        pos1: tuple[float, float, float], pos2: tuple[float, float, float]
    ) -> float:
        """
        Calculate Euclidean distance between two 3D positions.

        Args:
            pos1: (x, y, z) position 1 in meters
            pos2: (x, y, z) position 2 in meters

        Returns:
            Distance in meters
        """
        return float(
            np.sqrt(
                (pos2[0] - pos1[0]) ** 2
                + (pos2[1] - pos1[1]) ** 2
                + (pos2[2] - pos1[2]) ** 2
            )
        )
