"""MCS (Modulation and Coding Scheme) table support."""

from dataclasses import dataclass
from pathlib import Path
from typing import Optional
import csv
import logging

logger = logging.getLogger(__name__)

# Bits per symbol for each modulation scheme
MODULATION_BITS = {
    "bpsk": 1,
    "qpsk": 2,
    "16qam": 4,
    "64qam": 6,
    "256qam": 8,
    "1024qam": 10,
}


@dataclass(frozen=True)
class MCSEntry:
    """Single MCS table entry."""

    mcs_index: int
    modulation: str  # e.g., "bpsk", "qpsk", "16qam", "64qam", "256qam", "1024qam"
    code_rate: float  # e.g., 0.5, 0.75, 0.833
    min_snr_db: float  # Minimum SNR threshold for this MCS
    fec_type: str  # e.g., "ldpc", "none"
    bits_per_symbol: int  # Derived from modulation
    bandwidth_mhz: Optional[float] = None  # Optional, overrides interface bandwidth
    spreading_factor: Optional[int] = None  # For spread spectrum (future)
    processing_gain_db: Optional[float] = None  # For spread spectrum (future)

    @property
    def spectral_efficiency(self) -> float:
        """Return spectral efficiency (bits/symbol * code_rate)."""
        return self.bits_per_symbol * self.code_rate

    @classmethod
    def from_csv_row(cls, row: dict) -> "MCSEntry":
        """Create MCSEntry from CSV row dictionary."""
        modulation = row["modulation"].lower()
        bits = MODULATION_BITS.get(modulation, 6)

        # Handle optional bandwidth_mhz column
        bandwidth_mhz = None
        if "bandwidth_mhz" in row and row["bandwidth_mhz"]:
            bandwidth_mhz = float(row["bandwidth_mhz"])

        # Handle optional spread spectrum columns (future)
        spreading_factor = None
        if "spreading_factor" in row and row["spreading_factor"]:
            spreading_factor = int(row["spreading_factor"])

        processing_gain_db = None
        if "processing_gain_db" in row and row["processing_gain_db"]:
            processing_gain_db = float(row["processing_gain_db"])

        return cls(
            mcs_index=int(row["mcs_index"]),
            modulation=modulation,
            code_rate=float(row["code_rate"]),
            min_snr_db=float(row["min_snr_db"]),
            fec_type=row.get("fec_type", "ldpc").lower(),
            bits_per_symbol=bits,
            bandwidth_mhz=bandwidth_mhz,
            spreading_factor=spreading_factor,
            processing_gain_db=processing_gain_db,
        )


class MCSTable:
    """MCS lookup table with SNR-based selection."""

    DEFAULT_HYSTERESIS_DB = 2.0

    def __init__(self, entries: list[MCSEntry], hysteresis_db: float = 2.0):
        """
        Initialize MCS table.

        Args:
            entries: List of MCS entries (will be sorted by min_snr_db ascending)
            hysteresis_db: SNR hysteresis for stable MCS selection
        """
        self.entries = sorted(entries, key=lambda e: e.min_snr_db)
        self.hysteresis_db = hysteresis_db
        self._current_mcs: dict[str, int] = {}  # Track current MCS per link

        if not self.entries:
            raise ValueError("MCS table must have at least one entry")

    def reset_hysteresis(self) -> None:
        """Clear per-link MCS hysteresis history."""
        self._current_mcs.clear()

    @classmethod
    def from_csv(cls, csv_path: str | Path, hysteresis_db: float = 2.0) -> "MCSTable":
        """
        Load MCS table from CSV file.

        Args:
            csv_path: Path to CSV file
            hysteresis_db: SNR hysteresis value

        Returns:
            Loaded MCSTable
        """
        path = Path(csv_path)
        if not path.exists():
            raise FileNotFoundError(f"MCS table not found: {csv_path}")

        entries = []
        with open(path, newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                entries.append(MCSEntry.from_csv_row(row))

        logger.info(f"Loaded MCS table with {len(entries)} entries from {csv_path}")
        return cls(entries, hysteresis_db)

    def select_mcs(
        self,
        snr_db: float,
        link_id: Optional[str] = None,
    ) -> MCSEntry:
        """
        Select optimal MCS for given SNR.

        Uses hysteresis to prevent rapid switching if link_id is provided:
        - UPGRADE: SNR must exceed new MCS threshold by hysteresis_db margin
        - DOWNGRADE: SNR must drop below current MCS threshold by hysteresis_db margin

        Example with 2 dB hysteresis:
        - Currently at MCS 5 (min_snr=20 dB), MCS 6 threshold is 23 dB
        - To upgrade to MCS 6: SNR must be ≥ 25 dB (23 + 2)
        - To stay at MCS 5: SNR can be 18-24.99 dB
        - To downgrade from MCS 5: SNR must be < 18 dB (20 - 2)

        Args:
            snr_db: Current SNR in dB
            link_id: Optional link identifier for hysteresis tracking

        Returns:
            Selected MCSEntry
        """
        # Find highest MCS where SNR >= min_snr_db
        selected = self.entries[0]  # Default to lowest MCS

        for entry in self.entries:
            if snr_db >= entry.min_snr_db:
                selected = entry
            else:
                break

        # Apply hysteresis if we have history for this link
        if link_id and link_id in self._current_mcs:
            current_idx = self._current_mcs[link_id]
            new_idx = selected.mcs_index

            if new_idx > current_idx:
                # UPGRADE: Require SNR to exceed new threshold by hysteresis margin
                # This prevents rapid switching when SNR hovers near threshold
                if snr_db < (selected.min_snr_db + self.hysteresis_db):
                    # SNR not high enough for stable upgrade, stay at current MCS
                    current_entry = self.get_by_index(current_idx)
                    if current_entry:
                        selected = current_entry
            elif new_idx < current_idx:
                # DOWNGRADE: Allow if SNR dropped below current threshold minus margin
                # This prevents immediate downgrade on small SNR fluctuations
                current_entry = self.get_by_index(current_idx)
                if current_entry and snr_db >= (
                    current_entry.min_snr_db - self.hysteresis_db
                ):
                    # SNR still within margin, stay at current MCS
                    selected = current_entry

        if link_id:
            self._current_mcs[link_id] = selected.mcs_index

        return selected

    def get_by_index(self, mcs_index: int) -> Optional[MCSEntry]:
        """Get MCS entry by index."""
        for entry in self.entries:
            if entry.mcs_index == mcs_index:
                return entry
        return None

    def reset_link_state(self, link_id: str) -> None:
        """Reset hysteresis state for a link."""
        if link_id in self._current_mcs:
            del self._current_mcs[link_id]

    def reset_all_link_states(self) -> None:
        """Reset hysteresis state for all links."""
        self._current_mcs.clear()

    @property
    def max_mcs(self) -> MCSEntry:
        """Get highest MCS entry (highest SNR threshold)."""
        return self.entries[-1]

    @property
    def min_mcs(self) -> MCSEntry:
        """Get lowest MCS entry (lowest SNR threshold)."""
        return self.entries[0]

    def __len__(self) -> int:
        """Return number of MCS entries."""
        return len(self.entries)

    def __repr__(self) -> str:
        """Return string representation."""
        return f"MCSTable({len(self.entries)} entries, hysteresis={self.hysteresis_db}dB)"
