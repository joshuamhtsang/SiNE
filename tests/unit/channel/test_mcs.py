"""
Unit tests for mcs.py - MCS table and selection logic.

Tests MCS table loading, SNR-based selection, and hysteresis behavior.
"""

import pytest
from pathlib import Path
from sine.channel.mcs import MCSTable, MCSEntry, MODULATION_BITS


@pytest.fixture
def test_mcs_table_path() -> Path:
    """Return path to test MCS table."""
    return Path(__file__).parent.parent.parent / "fixtures" / "mcs_tables" / "test_mcs.csv"


@pytest.fixture
def mcs_table(test_mcs_table_path: Path) -> MCSTable:
    """Load test MCS table."""
    return MCSTable.from_csv(test_mcs_table_path, hysteresis_db=2.0)


class TestMCSEntry:
    """Test MCSEntry dataclass."""

    def test_mcs_entry_creation(self):
        """Test creating an MCS entry."""
        entry = MCSEntry(
            mcs_index=5,
            modulation="64qam",
            code_rate=0.5,
            min_snr_db=20.0,
            fec_type="ldpc",
            bits_per_symbol=6,
        )

        assert entry.mcs_index == 5
        assert entry.modulation == "64qam"
        assert entry.code_rate == 0.5
        assert entry.min_snr_db == 20.0
        assert entry.fec_type == "ldpc"
        assert entry.bits_per_symbol == 6

    def test_spectral_efficiency(self):
        """Test spectral efficiency calculation."""
        entry = MCSEntry(
            mcs_index=5,
            modulation="64qam",
            code_rate=0.5,
            min_snr_db=20.0,
            fec_type="ldpc",
            bits_per_symbol=6,
        )

        # Spectral efficiency = bits_per_symbol × code_rate = 6 × 0.5 = 3.0
        assert entry.spectral_efficiency == 3.0

    def test_from_csv_row_basic(self):
        """Test creating MCSEntry from CSV row."""
        row = {
            "mcs_index": "5",
            "modulation": "64qam",
            "code_rate": "0.5",
            "min_snr_db": "20.0",
            "fec_type": "ldpc",
        }

        entry = MCSEntry.from_csv_row(row)

        assert entry.mcs_index == 5
        assert entry.modulation == "64qam"
        assert entry.code_rate == 0.5
        assert entry.min_snr_db == 20.0
        assert entry.fec_type == "ldpc"
        assert entry.bits_per_symbol == 6  # Derived from modulation

    def test_from_csv_row_with_bandwidth(self):
        """Test CSV row with optional bandwidth_mhz field."""
        row = {
            "mcs_index": "5",
            "modulation": "64qam",
            "code_rate": "0.5",
            "min_snr_db": "20.0",
            "fec_type": "ldpc",
            "bandwidth_mhz": "80",
        }

        entry = MCSEntry.from_csv_row(row)
        assert entry.bandwidth_mhz == 80.0

    def test_from_csv_row_missing_fec_type(self):
        """Test that fec_type defaults to 'ldpc' if missing."""
        row = {
            "mcs_index": "5",
            "modulation": "64qam",
            "code_rate": "0.5",
            "min_snr_db": "20.0",
        }

        entry = MCSEntry.from_csv_row(row)
        assert entry.fec_type == "ldpc"  # Default

    def test_mcs_entry_frozen(self):
        """Test that MCSEntry is frozen (immutable)."""
        entry = MCSEntry(
            mcs_index=5,
            modulation="64qam",
            code_rate=0.5,
            min_snr_db=20.0,
            fec_type="ldpc",
            bits_per_symbol=6,
        )

        with pytest.raises(Exception):  # dataclass(frozen=True) raises FrozenInstanceError
            entry.mcs_index = 10


class TestMCSTableLoading:
    """Test MCS table loading from CSV."""

    def test_load_from_csv(self, test_mcs_table_path: Path):
        """Test loading MCS table from CSV file."""
        table = MCSTable.from_csv(test_mcs_table_path, hysteresis_db=2.0)

        assert len(table) == 10  # test_mcs.csv has 10 entries
        assert table.hysteresis_db == 2.0

    def test_load_nonexistent_file(self):
        """Test that loading nonexistent file raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            MCSTable.from_csv("/nonexistent/path.csv")

    def test_entries_sorted_by_snr(self, mcs_table: MCSTable):
        """Test that entries are sorted by min_snr_db ascending."""
        for i in range(len(mcs_table.entries) - 1):
            assert (
                mcs_table.entries[i].min_snr_db <= mcs_table.entries[i + 1].min_snr_db
            ), "MCS entries not sorted by SNR"

    def test_empty_table_raises_error(self):
        """Test that empty MCS table raises ValueError."""
        with pytest.raises(ValueError, match="at least one entry"):
            MCSTable(entries=[], hysteresis_db=2.0)

    def test_table_len(self, mcs_table: MCSTable):
        """Test table length."""
        assert len(mcs_table) == 10

    def test_table_repr(self, mcs_table: MCSTable):
        """Test table string representation."""
        repr_str = repr(mcs_table)
        assert "MCSTable" in repr_str
        assert "10 entries" in repr_str
        assert "hysteresis=2.0" in repr_str


class TestMCSSelection:
    """Test MCS selection based on SNR."""

    def test_select_lowest_mcs_below_all_thresholds(self, mcs_table: MCSTable):
        """Test that lowest MCS is selected when SNR is below all thresholds."""
        # MCS 0 has min_snr_db = 5.0
        mcs = mcs_table.select_mcs(snr_db=3.0)

        assert mcs.mcs_index == 0
        assert mcs.modulation == "bpsk"

    def test_select_highest_mcs_above_all_thresholds(self, mcs_table: MCSTable):
        """Test that highest MCS is selected when SNR is above all thresholds."""
        # MCS 9 has min_snr_db = 35.0
        mcs = mcs_table.select_mcs(snr_db=40.0)

        assert mcs.mcs_index == 9
        assert mcs.modulation == "1024qam"

    @pytest.mark.parametrize(
        "snr_db,expected_mcs_index",
        [
            (5.0, 0),  # At MCS 0 threshold
            (7.5, 0),  # Between MCS 0 and 1
            (8.0, 1),  # At MCS 1 threshold
            (10.5, 1),  # Between MCS 1 and 2
            (14.0, 3),  # At MCS 3 threshold
            (20.0, 5),  # At MCS 5 threshold
            (25.0, 6),  # Between MCS 6 and 7
            (35.0, 9),  # At MCS 9 threshold
        ],
    )
    def test_select_mcs_at_various_snr_levels(
        self, mcs_table: MCSTable, snr_db: float, expected_mcs_index: int
    ):
        """Test MCS selection at various SNR levels."""
        mcs = mcs_table.select_mcs(snr_db=snr_db)
        assert mcs.mcs_index == expected_mcs_index

    def test_select_mcs_exactly_at_threshold(self, mcs_table: MCSTable):
        """Test MCS selection when SNR exactly equals threshold."""
        # MCS 5 has min_snr_db = 20.0
        mcs = mcs_table.select_mcs(snr_db=20.0)
        assert mcs.mcs_index == 5

    def test_select_mcs_just_below_threshold(self, mcs_table: MCSTable):
        """Test MCS selection when SNR is just below threshold."""
        # Just below MCS 5 threshold (20.0)
        mcs = mcs_table.select_mcs(snr_db=19.99)
        assert mcs.mcs_index == 4  # Should select MCS 4

    def test_mcs_increases_with_snr(self, mcs_table: MCSTable):
        """Property: MCS should increase (or stay same) as SNR increases."""
        import numpy as np

        snr_values = np.linspace(0, 40, 50)
        mcs_indices = [mcs_table.select_mcs(s).mcs_index for s in snr_values]

        # Check monotonic increase
        for i in range(len(mcs_indices) - 1):
            assert mcs_indices[i] <= mcs_indices[i + 1], \
                f"MCS decreased from {mcs_indices[i]} to {mcs_indices[i+1]} at SNR {snr_values[i]}→{snr_values[i+1]}"


class TestMCSHysteresis:
    """Test MCS selection with hysteresis."""

    def test_upgrade_requires_hysteresis_margin(self, mcs_table: MCSTable):
        """Test that upgrading MCS requires SNR > threshold + hysteresis."""
        # Start at MCS 5 (min_snr = 20 dB), MCS 6 threshold = 23 dB
        # Hysteresis = 2 dB
        link_id = "link1"

        # First selection at SNR=20 dB → MCS 5
        mcs1 = mcs_table.select_mcs(snr_db=20.0, link_id=link_id)
        assert mcs1.mcs_index == 5

        # SNR increases to 24 dB (MCS 6 threshold is 23 dB)
        # To upgrade, need SNR >= 23 + 2 = 25 dB
        mcs2 = mcs_table.select_mcs(snr_db=24.0, link_id=link_id)
        assert mcs2.mcs_index == 5  # Should NOT upgrade (24 < 25)

        # SNR increases to 25 dB (meets hysteresis requirement)
        mcs3 = mcs_table.select_mcs(snr_db=25.0, link_id=link_id)
        assert mcs3.mcs_index == 6  # Should upgrade now

    def test_downgrade_with_hysteresis_margin(self, mcs_table: MCSTable):
        """Test that downgrading allows hysteresis margin below threshold."""
        link_id = "link2"

        # Start at high SNR, select MCS 6 (min_snr = 23 dB)
        mcs1 = mcs_table.select_mcs(snr_db=25.0, link_id=link_id)
        assert mcs1.mcs_index == 6

        # SNR drops to 21.5 dB (below threshold but within margin)
        # Downgrade threshold = 23 - 2 = 21 dB
        mcs2 = mcs_table.select_mcs(snr_db=21.5, link_id=link_id)
        assert mcs2.mcs_index == 6  # Should stay at MCS 6 (21.5 > 21)

        # SNR drops to 20.5 dB (below downgrade threshold)
        mcs3 = mcs_table.select_mcs(snr_db=20.5, link_id=link_id)
        assert mcs3.mcs_index == 5  # Should downgrade to MCS 5

    def test_no_hysteresis_without_link_id(self, mcs_table: MCSTable):
        """Test that hysteresis is not applied without link_id."""
        # Without link_id, should select purely based on SNR
        mcs1 = mcs_table.select_mcs(snr_db=23.0)  # MCS 6 threshold
        assert mcs1.mcs_index == 6

        # Slightly below threshold
        mcs2 = mcs_table.select_mcs(snr_db=22.9)
        assert mcs2.mcs_index == 5  # Immediately downgrades (no hysteresis)

    def test_different_links_independent_hysteresis(self, mcs_table: MCSTable):
        """Test that different links maintain independent hysteresis state."""
        # Link 1 at MCS 5
        mcs_link1 = mcs_table.select_mcs(snr_db=20.0, link_id="link1")
        assert mcs_link1.mcs_index == 5

        # Link 2 at MCS 8
        mcs_link2 = mcs_table.select_mcs(snr_db=30.0, link_id="link2")
        assert mcs_link2.mcs_index == 8

        # Both links should maintain their state independently
        mcs_link1_again = mcs_table.select_mcs(snr_db=20.0, link_id="link1")
        mcs_link2_again = mcs_table.select_mcs(snr_db=30.0, link_id="link2")

        assert mcs_link1_again.mcs_index == 5
        assert mcs_link2_again.mcs_index == 8

    def test_reset_link_state(self, mcs_table: MCSTable):
        """Test resetting hysteresis state for a link."""
        link_id = "link1"

        # Select MCS 5
        mcs1 = mcs_table.select_mcs(snr_db=20.0, link_id=link_id)
        assert mcs1.mcs_index == 5

        # Reset state
        mcs_table.reset_link_state(link_id)

        # Now SNR=24 should select MCS 6 immediately (no hysteresis)
        mcs2 = mcs_table.select_mcs(snr_db=24.0, link_id=link_id)
        assert mcs2.mcs_index == 6

    def test_reset_all_link_states(self, mcs_table: MCSTable):
        """Test resetting all link states."""
        # Set up multiple links
        mcs_table.select_mcs(snr_db=20.0, link_id="link1")
        mcs_table.select_mcs(snr_db=25.0, link_id="link2")
        mcs_table.select_mcs(snr_db=30.0, link_id="link3")

        # Reset all
        mcs_table.reset_all_link_states()

        # All links should behave as if first selection (no hysteresis)
        assert mcs_table._current_mcs == {}


class TestMCSTableProperties:
    """Test MCS table properties and utility methods."""

    def test_min_mcs(self, mcs_table: MCSTable):
        """Test getting minimum MCS entry."""
        min_mcs = mcs_table.min_mcs
        assert min_mcs.mcs_index == 0
        assert min_mcs.modulation == "bpsk"
        assert min_mcs.min_snr_db == 5.0

    def test_max_mcs(self, mcs_table: MCSTable):
        """Test getting maximum MCS entry."""
        max_mcs = mcs_table.max_mcs
        assert max_mcs.mcs_index == 9
        assert max_mcs.modulation == "1024qam"
        assert max_mcs.min_snr_db == 35.0

    def test_get_by_index_valid(self, mcs_table: MCSTable):
        """Test getting MCS entry by index."""
        mcs = mcs_table.get_by_index(5)
        assert mcs is not None
        assert mcs.mcs_index == 5
        assert mcs.modulation == "64qam"

    def test_get_by_index_invalid(self, mcs_table: MCSTable):
        """Test that invalid index returns None."""
        mcs = mcs_table.get_by_index(99)
        assert mcs is None

    def test_get_by_index_all_entries(self, mcs_table: MCSTable):
        """Test that all entries can be retrieved by index."""
        for i in range(10):
            mcs = mcs_table.get_by_index(i)
            assert mcs is not None
            assert mcs.mcs_index == i


class TestModulationBitsConstant:
    """Test MODULATION_BITS constant."""

    def test_modulation_bits_mapping(self):
        """Test that MODULATION_BITS has correct values."""
        assert MODULATION_BITS["bpsk"] == 1
        assert MODULATION_BITS["qpsk"] == 2
        assert MODULATION_BITS["16qam"] == 4
        assert MODULATION_BITS["64qam"] == 6
        assert MODULATION_BITS["256qam"] == 8
        assert MODULATION_BITS["1024qam"] == 10

    def test_all_modulations_covered(self):
        """Test that all common modulations are in MODULATION_BITS."""
        expected_mods = {"bpsk", "qpsk", "16qam", "64qam", "256qam", "1024qam"}
        assert set(MODULATION_BITS.keys()) == expected_mods


class TestMCSHysteresisEdgeCases:
    """Test edge cases in hysteresis logic."""

    def test_hysteresis_zero(self):
        """Test with zero hysteresis (immediate switching)."""
        table = MCSTable(
            entries=[
                MCSEntry(0, "bpsk", 0.5, 5.0, "ldpc", 1),
                MCSEntry(1, "qpsk", 0.5, 10.0, "ldpc", 2),
            ],
            hysteresis_db=0.0,
        )

        link_id = "link1"

        # Start at MCS 0
        mcs1 = table.select_mcs(snr_db=5.0, link_id=link_id)
        assert mcs1.mcs_index == 0

        # SNR exactly at MCS 1 threshold (0dB hysteresis → immediate upgrade)
        mcs2 = table.select_mcs(snr_db=10.0, link_id=link_id)
        assert mcs2.mcs_index == 1

    def test_large_hysteresis(self):
        """Test with large hysteresis (sticky MCS)."""
        table = MCSTable(
            entries=[
                MCSEntry(0, "bpsk", 0.5, 5.0, "ldpc", 1),
                MCSEntry(1, "qpsk", 0.5, 10.0, "ldpc", 2),
                MCSEntry(2, "16qam", 0.5, 15.0, "ldpc", 4),
            ],
            hysteresis_db=10.0,  # Large hysteresis
        )

        link_id = "link1"

        # Start at MCS 1
        mcs1 = table.select_mcs(snr_db=10.0, link_id=link_id)
        assert mcs1.mcs_index == 1

        # To upgrade to MCS 2 (threshold 15), need 15 + 10 = 25 dB
        mcs2 = table.select_mcs(snr_db=20.0, link_id=link_id)
        assert mcs2.mcs_index == 1  # Should stay at MCS 1 (20 < 25)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
