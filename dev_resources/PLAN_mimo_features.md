# Plan: MIMO (Multiple-Input Multiple-Output) Support for SiNE

## Executive Summary

Add MIMO capabilities to SiNE's wireless channel emulation, enabling spatial multiplexing (higher throughput) and diversity gains (improved reliability) for WiFi 6 and 5G network scenarios. Implementation will be phased to balance complexity with incremental validation.

**Key Insight from Expert Consultation**: Skip naive rate scaling (Phase 1) and start with eigenvalue-based MIMO channel matrix processing (Phase 2) for realistic modeling from day 1.

---

## Current State (SISO Architecture)

### Hardcoded Single-Antenna Configuration

**Location**: `src/sine/channel/sionna_engine.py:187-194` (TX), `228-235` (RX)

```python
tx_array = PlanarArray(
    num_rows=1,      # ← Hardcoded SISO
    num_cols=1,
    vertical_spacing=0.5,
    horizontal_spacing=0.5,
    pattern=antenna_pattern,
    polarization=polarization,
)
```

### Current Pipeline

```
Sionna RT (1×1 arrays) → CIR (scalar) → Path Loss → SNR → BER → PER → Netem (rate, loss%)
```

**Channel matrix reduction**: `sionna_engine.py:299-320`
- Incoherent power summation: `Σ|aᵢ|²` across paths (correct for OFDM)
- Collapses spatial information to scalar path loss

### Schema Constraints

**Location**: `src/sine/config/schema.py:272-296`

- `antenna_pattern` XOR `antenna_gain_dbi` (mutually exclusive)
- No multi-antenna configuration
- Validation enforces exactly one antenna type per interface

---

## Target MIMO Architecture

### What Sionna RT Already Supports

Sionna's `PlanarArray` supports arbitrary M×N antenna arrays:
- Full MIMO channel matrix: `a[num_rx_ant, num_tx_ant, num_paths]`
- Currently collapsed via `synthetic_array=True` (4D indexing)
- Need `synthetic_array=False` for 6D indexing to preserve spatial info

### MIMO Pipeline

```
Sionna RT (M×N arrays) → CIR (MIMO matrix H) → Eigenvalues → Effective SNR → BER → PER → Netem
                                                     ↓
                                          Diversity Gain + Spatial Multiplexing
```

**Key Metrics**:
- **Eigenvalues** (λ₁, λ₂, ...): Spatial channel strengths
- **Channel Rank**: Number of effective spatial streams
- **Effective SNR**: Per-stream SNR accounting for power splitting and inter-stream interference

---

## Phased Implementation Plan

### Phase 1: Schema Extensions for MIMO Configuration

**Goal**: Add antenna array configuration to support 2×2, 4×4 MIMO

#### 1.1 New Configuration Classes

**Location**: `src/sine/config/schema.py` (add after line ~120)

```python
class AntennaArrayConfig(BaseModel):
    """Multi-antenna array configuration for MIMO."""

    num_rows: int = Field(
        default=1,
        ge=1,
        le=8,
        description="Number of antenna rows (vertical dimension)"
    )
    num_cols: int = Field(
        default=1,
        ge=1,
        le=8,
        description="Number of antenna columns (horizontal dimension)"
    )
    vertical_spacing_wavelengths: float = Field(
        default=0.5,
        ge=0.1,
        le=2.0,
        description="Vertical spacing between elements in wavelengths (0.5 = λ/2)"
    )
    horizontal_spacing_wavelengths: float = Field(
        default=0.5,
        ge=0.1,
        le=2.0,
        description="Horizontal spacing in wavelengths"
    )
    element_pattern: AntennaPattern = Field(
        default=AntennaPattern.ISO,
        description="Antenna pattern for each array element"
    )
    polarization: Polarization = Field(
        default=Polarization.V,
        description="Polarization for all elements"
    )

    @property
    def num_antennas(self) -> int:
        """Total number of antenna elements."""
        return self.num_rows * self.num_cols


class MIMOConfig(BaseModel):
    """MIMO processing configuration."""

    num_spatial_streams: int = Field(
        default=1,
        ge=1,
        le=8,
        description="Number of spatial streams (must be ≤ min(num_tx_ant, num_rx_ant))"
    )
    receiver_type: str = Field(
        default="mmse",
        description="MIMO receiver type: mmse (recommended), zf (zero-forcing), or mrc (diversity only)"
    )
    enable_rank_adaptation: bool = Field(
        default=True,
        description="Dynamically reduce streams if channel rank < num_spatial_streams"
    )
    correlation_coefficient: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Antenna correlation (0 = uncorrelated, 1 = fully correlated)"
    )
```

#### 1.2 Extend WirelessParams

**Location**: `src/sine/config/schema.py` (modify `WirelessParams` class, ~line 180)

**Add fields**:
```python
# MIMO antenna configuration (mutually exclusive with SISO antenna_pattern/antenna_gain_dbi)
tx_antenna_array: AntennaArrayConfig | None = Field(
    default=None,
    description="Transmit antenna array (MIMO). Mutually exclusive with antenna_pattern/antenna_gain_dbi"
)
rx_antenna_array: AntennaArrayConfig | None = Field(
    default=None,
    description="Receive antenna array (MIMO). Mutually exclusive with antenna_pattern/antenna_gain_dbi"
)
mimo_config: MIMOConfig | None = Field(
    default=None,
    description="MIMO processing config (required if tx_antenna_array or rx_antenna_array is set)"
)
```

#### 1.3 Update Validation Logic

**Location**: `src/sine/config/schema.py:272-296` (modify `validate_antenna_config()`)

**New validation rules**:
```python
@model_validator(mode="after")
def validate_antenna_config(self) -> "WirelessParams":
    """Ensure exactly one antenna configuration mode: SISO or MIMO."""
    has_pattern = self.antenna_pattern is not None
    has_gain = self.antenna_gain_dbi is not None
    has_tx_array = self.tx_antenna_array is not None
    has_rx_array = self.rx_antenna_array is not None
    has_mimo = has_tx_array or has_rx_array

    # SISO validation (existing logic)
    if not has_mimo:
        if not has_pattern and not has_gain:
            raise ValueError("Wireless interface requires antenna configuration...")
        if has_pattern and has_gain:
            raise ValueError("Cannot specify both antenna_pattern and antenna_gain_dbi...")
        return self

    # MIMO validation (new logic)
    if has_mimo:
        if has_pattern or has_gain:
            raise ValueError(
                "Cannot mix MIMO antenna arrays (tx_antenna_array/rx_antenna_array) "
                "with SISO antenna config (antenna_pattern/antenna_gain_dbi). "
                "Use one mode or the other."
            )

        if not has_tx_array or not has_rx_array:
            raise ValueError(
                "MIMO requires both tx_antenna_array and rx_antenna_array. "
                "For SISO, use antenna_pattern or antenna_gain_dbi instead."
            )

        if self.mimo_config is None:
            raise ValueError(
                "mimo_config is required when using MIMO antenna arrays."
            )

        # Validate num_spatial_streams
        num_tx_ant = self.tx_antenna_array.num_antennas
        num_rx_ant = self.rx_antenna_array.num_antennas
        max_streams = min(num_tx_ant, num_rx_ant)

        if self.mimo_config.num_spatial_streams > max_streams:
            raise ValueError(
                f"num_spatial_streams ({self.mimo_config.num_spatial_streams}) "
                f"cannot exceed min(num_tx_ant={num_tx_ant}, num_rx_ant={num_rx_ant})={max_streams}"
            )

    return self
```

**Files Modified**: `src/sine/config/schema.py`

---

### Phase 2: MIMO Channel Computation Engine

**Goal**: Enable Sionna RT to compute full MIMO channel matrix and extract eigenvalues

#### 2.1 Extend SionnaEngine for MIMO Arrays

**Location**: `src/sine/channel/sionna_engine.py`

**Modify `add_transmitter()` (lines 163-202)**:
```python
def add_transmitter(
    self,
    name: str,
    position: tuple[float, float, float],
    antenna_pattern: str = "iso",
    polarization: str = "V",
    # NEW MIMO parameters
    num_antenna_rows: int = 1,
    num_antenna_cols: int = 1,
    antenna_spacing_wavelengths: float = 0.5,
) -> None:
    """Add transmitter with optional MIMO antenna array."""

    # Create antenna array (support SISO and MIMO)
    tx_array = PlanarArray(
        num_rows=num_antenna_rows,      # ← Dynamic, not hardcoded
        num_cols=num_antenna_cols,
        vertical_spacing=antenna_spacing_wavelengths,
        horizontal_spacing=antenna_spacing_wavelengths,
        pattern=antenna_pattern,
        polarization=polarization,
    )

    # ... rest of setup (unchanged)
```

**Modify `add_receiver()` similarly** (lines 204-243)

#### 2.2 New MIMO Channel Matrix Extraction

**Location**: `src/sine/channel/sionna_engine.py` (add new method after `compute_paths()`)

```python
def compute_mimo_channel_matrix(self) -> MIMOChannelResult:
    """
    Compute full MIMO channel matrix H from Sionna RT paths.

    Returns:
        MIMOChannelResult with channel matrix, eigenvalues, and MIMO metrics
    """
    if not self._scene_loaded:
        raise RuntimeError("Scene must be loaded before computing MIMO channel")

    # Get CIR with full spatial dimensions
    # Note: synthetic_array=True (default) collapses antennas to single channel
    # For MIMO, we need synthetic_array=False to get per-antenna coefficients
    paths = self.path_solver(self.scene)
    cir_result = paths.cir(out_type='numpy')

    if isinstance(cir_result, tuple) and len(cir_result) == 2:
        a_np, tau_np = cir_result
    else:
        raise ValueError("Unexpected CIR format from Sionna")

    # Handle real/imaginary split
    if isinstance(a_np, tuple) and len(a_np) == 2:
        a_np = a_np[0] + 1j * a_np[1]

    if not np.iscomplexobj(a_np):
        a_np = a_np.astype(np.complex128)

    # CIR shape: [num_rx, num_rx_ant, num_tx, num_tx_ant, num_paths, num_time_steps]
    # For single TX/RX pair: [1, num_rx_ant, 1, num_tx_ant, num_paths, num_time_steps]

    # Aggregate across paths to get frequency-domain channel matrix
    # H(f) = Σ_paths [a_i × e^(-j2πfτ_i)] for each (rx_ant, tx_ant) pair
    # For network emulation, use frequency-averaged (wideband) channel

    # Extract spatial channel matrix (sum path powers incoherently per antenna pair)
    # Shape: [num_rx_ant, num_tx_ant]
    H = self._extract_spatial_channel_matrix(a_np, tau_np)

    # Compute eigenvalues of H @ H^H (receive covariance matrix)
    eigenvalues = np.linalg.eigvalsh(H @ H.conj().T)
    eigenvalues_sorted = np.sort(eigenvalues)[::-1]  # Descending order

    # Channel rank (number of significant eigenmodes)
    rank_threshold = 0.1  # Eigenvalues < 10% of largest are considered noise
    rank = np.sum(eigenvalues_sorted > rank_threshold * eigenvalues_sorted[0])

    # Condition number (affects precoding gains)
    condition_number = float(eigenvalues_sorted[0] / (eigenvalues_sorted[-1] + 1e-12))

    return MIMOChannelResult(
        channel_matrix=H,
        eigenvalues=eigenvalues_sorted.tolist(),
        rank=int(rank),
        condition_number=condition_number,
        num_tx_antennas=H.shape[1],
        num_rx_antennas=H.shape[0],
    )


def _extract_spatial_channel_matrix(
    self,
    a: np.ndarray,
    tau: np.ndarray,
) -> np.ndarray:
    """
    Extract spatial channel matrix from CIR.

    For OFDM with cyclic prefix, use incoherent power summation across paths
    per antenna pair (correct for frequency-flat per-subcarrier model).

    Args:
        a: CIR amplitudes [num_rx, num_rx_ant, num_tx, num_tx_ant, num_paths, ...]
        tau: Path delays [num_rx, num_rx_ant, num_tx, num_tx_ant, num_paths]

    Returns:
        H: Spatial channel matrix [num_rx_ant, num_tx_ant] with complex coefficients
    """
    # Assume single TX/RX pair (index 0)
    a_single_link = a[0, :, 0, :, :, ...]  # [num_rx_ant, num_tx_ant, num_paths, ...]

    # Sum path powers incoherently per antenna pair
    # For each (rx_ant, tx_ant): h_ij = sqrt(Σ |a_ijk|²) × e^(jφ_ij)
    # Phase φ_ij from dominant path

    num_rx_ant, num_tx_ant, num_paths = a_single_link.shape[:3]
    H = np.zeros((num_rx_ant, num_tx_ant), dtype=np.complex128)

    for i in range(num_rx_ant):
        for j in range(num_tx_ant):
            # Get path coefficients for this antenna pair
            a_ij = a_single_link[i, j, :]  # [num_paths, ...]

            # Flatten time dimension if present
            if a_ij.ndim > 1:
                a_ij = a_ij[:, 0]  # Take first time sample

            # Incoherent power sum (OFDM model)
            path_powers = np.abs(a_ij) ** 2
            total_power = np.sum(path_powers)

            # Use phase of strongest path (dominant path approximation)
            dominant_path_idx = np.argmax(path_powers)
            dominant_phase = np.angle(a_ij[dominant_path_idx])

            # Composite channel coefficient
            H[i, j] = np.sqrt(total_power) * np.exp(1j * dominant_phase)

    return H
```

#### 2.3 New Data Structures

**Location**: `src/sine/channel/sionna_engine.py` (add after `PathResult` definition, ~line 71)

```python
@dataclass
class MIMOChannelResult:
    """MIMO channel computation result."""

    channel_matrix: np.ndarray  # [num_rx_ant, num_tx_ant] complex matrix
    eigenvalues: list[float]    # Sorted descending
    rank: int                   # Number of significant spatial modes
    condition_number: float     # λ_max / λ_min (1 = well-conditioned)
    num_tx_antennas: int
    num_rx_antennas: int

    @property
    def is_rank_deficient(self) -> bool:
        """Check if channel has rank deficiency (e.g., LOS)."""
        return self.rank < min(self.num_tx_antennas, self.num_rx_antennas)
```

**Files Modified**: `src/sine/channel/sionna_engine.py`

---

### Phase 3: MIMO Effective SNR Calculation

**Goal**: Convert MIMO channel eigenvalues to effective SNR for MCS selection

#### 3.1 New MIMO SNR Calculator

**Location**: `src/sine/channel/snr.py` (add new method to `SNRCalculator` class)

```python
def calculate_mimo_effective_snr(
    self,
    mimo_result: MIMOChannelResult,
    snr_siso_db: float,
    num_streams: int,
    receiver_type: str = "mmse",
) -> tuple[float, dict]:
    """
    Calculate effective SNR for MIMO spatial multiplexing.

    Args:
        mimo_result: MIMO channel result with eigenvalues
        snr_siso_db: SNR from link budget (single-antenna baseline)
        num_streams: Number of spatial streams to use
        receiver_type: "mmse" (MMSE), "zf" (zero-forcing), or "mrc" (diversity only)

    Returns:
        Tuple of (effective_snr_db, mimo_metrics_dict)
    """
    eigenvalues = np.array(mimo_result.eigenvalues)
    snr_linear = 10 ** (snr_siso_db / 10)

    # Validate num_streams
    num_streams_effective = min(num_streams, mimo_result.rank)
    if num_streams_effective < num_streams:
        logger.warning(
            f"Channel rank ({mimo_result.rank}) < requested streams ({num_streams}). "
            f"Using {num_streams_effective} streams."
        )

    # Power splitting penalty: TX power divided across streams
    snr_per_stream_linear = snr_linear / num_streams_effective

    if receiver_type == "mrc":
        # Maximal Ratio Combining (diversity only, 1 stream)
        # Effective SNR = sum of all eigenvalues × SNR
        diversity_gain_linear = np.sum(eigenvalues) / mimo_result.num_rx_antennas
        effective_snr_linear = diversity_gain_linear * snr_linear
        effective_snr_db = 10 * np.log10(effective_snr_linear)

        mimo_metrics = {
            "diversity_gain_db": 10 * np.log10(diversity_gain_linear),
            "num_streams_used": 1,
            "receiver_type": "mrc",
        }

    elif receiver_type == "mmse":
        # MMSE receiver: accounts for inter-stream interference
        effective_snrs = []

        for i in range(num_streams_effective):
            # Signal power from stream i
            signal_power = eigenvalues[i]

            # Inter-stream interference (from other streams)
            if num_streams_effective > 1:
                interference_streams = eigenvalues[num_streams_effective:]
                interference_power = np.sum(interference_streams) / num_streams_effective
            else:
                interference_power = 0.0

            # Noise power (normalized)
            noise_power = 1.0 / snr_per_stream_linear

            # MMSE effective SINR for stream i
            sinr_i_linear = signal_power / (noise_power + interference_power)
            effective_snrs.append(10 * np.log10(sinr_i_linear))

        # Use worst-case stream SNR (determines overall PER)
        effective_snr_db = min(effective_snrs)

        mimo_metrics = {
            "per_stream_snrs_db": effective_snrs,
            "num_streams_used": num_streams_effective,
            "receiver_type": "mmse",
            "power_penalty_db": -10 * np.log10(num_streams_effective),
        }

    elif receiver_type == "zf":
        # Zero-Forcing: amplifies noise on weak eigenmodes
        weakest_eigenvalue = eigenvalues[num_streams_effective - 1]
        effective_snr_linear = weakest_eigenvalue * snr_per_stream_linear
        effective_snr_db = 10 * np.log10(effective_snr_linear)

        mimo_metrics = {
            "weakest_eigenvalue": float(weakest_eigenvalue),
            "num_streams_used": num_streams_effective,
            "receiver_type": "zf",
        }

    else:
        raise ValueError(f"Unknown receiver type: {receiver_type}")

    mimo_metrics.update({
        "channel_rank": mimo_result.rank,
        "condition_number": mimo_result.condition_number,
        "eigenvalues": mimo_result.eigenvalues[:num_streams_effective],
    })

    return effective_snr_db, mimo_metrics
```

**Files Modified**: `src/sine/channel/snr.py`

---

### Phase 4: MIMO Rate Calculation

**Goal**: Scale throughput by number of spatial streams

#### 4.1 Extend Rate Calculator

**Location**: `src/sine/channel/per_calculator.py` (modify `calculate_effective_rate()`)

**Current signature** (~line 113):
```python
@staticmethod
def calculate_effective_rate(
    bandwidth_mhz: float,
    modulation_bits: int,
    code_rate: float,
    per: float,
) -> float:
```

**New signature**:
```python
@staticmethod
def calculate_effective_rate(
    bandwidth_mhz: float,
    modulation_bits: int,
    code_rate: float,
    per: float,
    num_spatial_streams: int = 1,  # NEW: MIMO spatial multiplexing
) -> float:
    """
    Calculate effective data rate accounting for MIMO spatial streams.

    Args:
        bandwidth_mhz: Channel bandwidth in MHz
        modulation_bits: Bits per symbol (BPSK=1, QPSK=2, 16QAM=4, etc.)
        code_rate: FEC code rate (0.0 to 1.0)
        per: Packet error rate (0.0 to 1.0)
        num_spatial_streams: Number of MIMO spatial streams (1 for SISO)

    Returns:
        Effective rate in Mbps
    """
    # Base rate per stream
    raw_rate_per_stream = bandwidth_mhz * modulation_bits * 0.8  # 0.8 = OFDM efficiency
    coded_rate_per_stream = raw_rate_per_stream * code_rate
    effective_rate_per_stream = coded_rate_per_stream * (1.0 - per)

    # MIMO spatial multiplexing: multiply by number of streams
    effective_rate_total = effective_rate_per_stream * num_spatial_streams

    return effective_rate_total
```

**Files Modified**: `src/sine/channel/per_calculator.py`

---

### Phase 5: Server API Integration

**Goal**: Wire MIMO processing into channel server endpoints

#### 5.1 Extend Request/Response Models

**Location**: `src/sine/channel/server.py`

**Extend `WirelessLinkRequest`** (~line 134):
```python
class WirelessLinkRequest(BaseModel):
    # ... existing fields ...

    # MIMO configuration (optional, defaults to SISO)
    num_tx_antennas: int = Field(default=1, ge=1, le=8)
    num_rx_antennas: int = Field(default=1, ge=1, le=8)
    num_spatial_streams: int = Field(default=1, ge=1, le=8)
    mimo_receiver_type: str = Field(default="mmse", description="mmse, zf, or mrc")
    antenna_spacing_wavelengths: float = Field(default=0.5, ge=0.1, le=2.0)
```

**Extend `ChannelResponse`** (~line 167):
```python
class ChannelResponse(BaseModel):
    # ... existing fields ...

    # MIMO metrics (populated when MIMO is enabled)
    mimo_enabled: bool = False
    num_tx_antennas: int = 1
    num_rx_antennas: int = 1
    num_spatial_streams_used: int = 1
    channel_rank: int | None = None
    condition_number: float | None = None
    eigenvalues: list[float] | None = None
    mimo_diversity_gain_db: float | None = None
```

#### 5.2 Modify Channel Computation Pipeline

**Location**: `src/sine/channel/server.py` (modify `compute_channel_for_link()`, ~line 915)

**Current flow**:
```python
# 1. Compute paths → PathResult (scalar path loss)
# 2. Calculate SNR from path loss
# 3. Compute BER/BLER/PER
# 4. Calculate rate
```

**New MIMO flow**:
```python
def compute_channel_for_link(...):
    # ... existing setup ...

    # Detect MIMO mode
    is_mimo = link.num_tx_antennas > 1 or link.num_rx_antennas > 1

    if is_mimo:
        # MIMO pipeline
        # 1. Configure Sionna engine with MIMO arrays
        engine.add_transmitter(
            name=link.tx_node,
            position=link.tx_position,
            antenna_pattern=link.antenna_pattern,
            polarization=link.polarization,
            num_antenna_rows=link.num_tx_antennas,  # NEW
            num_antenna_cols=1,
            antenna_spacing_wavelengths=link.antenna_spacing_wavelengths,
        )

        engine.add_receiver(
            name=link.rx_node,
            position=link.rx_position,
            antenna_pattern=link.antenna_pattern,
            polarization=link.polarization,
            num_antenna_rows=link.num_rx_antennas,  # NEW
            num_antenna_cols=1,
            antenna_spacing_wavelengths=link.antenna_spacing_wavelengths,
        )

        # 2. Compute MIMO channel matrix
        mimo_result = engine.compute_mimo_channel_matrix()

        # 3. Get SISO baseline path loss (for comparison)
        path_result = engine.compute_paths()  # Still compute for delay info

        # 4. Calculate SISO SNR
        snr_calc = SNRCalculator(...)
        rx_power, snr_siso_db = snr_calc.calculate_link_snr(
            tx_power_dbm=link.tx_power_dbm,
            path_loss_db=path_result.path_loss_db,
            tx_gain_dbi=0.0,  # Gain already in Sionna
            rx_gain_dbi=0.0,
        )

        # 5. Calculate MIMO effective SNR
        effective_snr_db, mimo_metrics = snr_calc.calculate_mimo_effective_snr(
            mimo_result=mimo_result,
            snr_siso_db=snr_siso_db,
            num_streams=link.num_spatial_streams,
            receiver_type=link.mimo_receiver_type,
        )

        # Use effective SNR for MCS selection
        metric_for_mcs = effective_snr_db

        # ... rest of pipeline (BER, BLER, PER) uses effective_snr_db ...

        # 6. Calculate rate with spatial multiplexing
        rate_mbps = PERCalculator.calculate_effective_rate(
            bandwidth_mhz=link.bandwidth_hz / 1e6,
            modulation_bits=modulation_bits,
            code_rate=fec_code_rate,
            per=per,
            num_spatial_streams=mimo_metrics["num_streams_used"],  # NEW
        )

        # 7. Populate MIMO metrics in response
        response.mimo_enabled = True
        response.num_tx_antennas = link.num_tx_antennas
        response.num_rx_antennas = link.num_rx_antennas
        response.num_spatial_streams_used = mimo_metrics["num_streams_used"]
        response.channel_rank = mimo_metrics["channel_rank"]
        response.eigenvalues = mimo_metrics["eigenvalues"]
        # ... etc ...

    else:
        # SISO pipeline (existing code, unchanged)
        # ... existing logic ...
```

**Files Modified**: `src/sine/channel/server.py`

---

### Phase 6: MIMO MCS Tables (Optional Extension)

**Goal**: WiFi 6 MCS tables with spatial stream variants

#### 6.1 Extended MCS Table Format

**Location**: Create `examples/wifi6_mimo/wifi6_mcs_mimo.csv`

```csv
mcs_index,modulation,code_rate,min_snr_db,fec_type,bandwidth_mhz,num_streams
0,bpsk,0.5,5.0,ldpc,80,1
0,bpsk,0.5,2.0,ldpc,80,2
0,bpsk,0.5,0.0,ldpc,80,4
5,64qam,0.667,20.0,ldpc,80,1
5,64qam,0.667,17.0,ldpc,80,2
5,64qam,0.667,14.0,ldpc,80,4
11,1024qam,0.833,38.0,ldpc,80,1
11,1024qam,0.833,35.0,ldpc,80,2
11,1024qam,0.833,32.0,ldpc,80,4
```

**Key insight**: SNR thresholds decrease with more streams due to diversity gain.

#### 6.2 MCS Selection with Streams

**Location**: `src/sine/channel/modulation.py` (extend `MCSTable.select_mcs()`)

**Current**: Selects MCS based on SNR only
**New**: Filter by `num_streams` first, then select by SNR

```python
def select_mcs(
    self,
    snr_db: float,
    link_id: str,
    num_streams: int = 1,  # NEW parameter
) -> MCSEntry:
    """Select MCS based on SNR and number of spatial streams."""

    # Filter MCS table for matching num_streams
    valid_entries = [
        entry for entry in self.entries
        if entry.num_streams == num_streams  # NEW filter
    ]

    if not valid_entries:
        raise ValueError(f"No MCS entries for {num_streams} spatial streams")

    # Select highest MCS where snr_db >= min_snr_db + hysteresis
    # ... existing logic ...
```

**Files Modified**: `src/sine/channel/modulation.py`

---

## Testing Strategy

### Unit Tests

**Location**: `tests/channel/test_mimo_*.py` (new files)

#### Test 1: MIMO Channel Matrix Computation

```python
def test_mimo_channel_matrix_2x2():
    """Test 2×2 MIMO channel matrix extraction from Sionna."""
    engine = SionnaEngine()
    engine.load_scene("scenes/vacuum.xml")

    # Add 2×2 arrays
    engine.add_transmitter("tx", (0, 0, 1), num_antenna_rows=2, num_antenna_cols=1)
    engine.add_receiver("rx", (20, 0, 1), num_antenna_rows=2, num_antenna_cols=1)

    # Compute MIMO channel
    mimo_result = engine.compute_mimo_channel_matrix()

    assert mimo_result.channel_matrix.shape == (2, 2)
    assert mimo_result.num_tx_antennas == 2
    assert mimo_result.num_rx_antennas == 2
    assert len(mimo_result.eigenvalues) == 2
    assert mimo_result.rank >= 1  # At least 1 eigenmode
```

#### Test 2: LOS Rank Deficiency

```python
def test_mimo_los_rank_deficiency():
    """Verify LOS channel is rank-1 (not full rank for 2×2)."""
    # ... setup 2×2 MIMO in free space (LOS) ...

    mimo_result = engine.compute_mimo_channel_matrix()

    # LOS should be rank-1 (single dominant eigenvalue)
    assert mimo_result.rank == 1
    assert mimo_result.eigenvalues[0] / mimo_result.eigenvalues[1] > 10  # 10 dB gap
```

#### Test 3: Rich Multipath Full Rank

```python
def test_mimo_rich_multipath_full_rank():
    """Verify rich indoor multipath gives full rank channel."""
    # ... setup 2×2 MIMO in two_rooms.xml (rich scattering) ...

    mimo_result = engine.compute_mimo_channel_matrix()

    # Rich scattering should give full rank
    assert mimo_result.rank == 2
    assert mimo_result.eigenvalues[1] / mimo_result.eigenvalues[0] > 0.3  # Within 5 dB
```

#### Test 4: MIMO Effective SNR

```python
def test_mimo_effective_snr_mmse():
    """Test MMSE effective SNR calculation."""
    # Mock MIMO result
    H = np.array([[1.0, 0.1], [0.1, 1.0]], dtype=np.complex128)
    eigenvalues = np.linalg.eigvalsh(H @ H.conj().T)

    mimo_result = MIMOChannelResult(
        channel_matrix=H,
        eigenvalues=sorted(eigenvalues, reverse=True),
        rank=2,
        condition_number=1.1,
        num_tx_antennas=2,
        num_rx_antennas=2,
    )

    snr_calc = SNRCalculator(bandwidth_hz=80e6, noise_figure_db=7.0)
    snr_siso_db = 20.0

    effective_snr_db, metrics = snr_calc.calculate_mimo_effective_snr(
        mimo_result, snr_siso_db, num_streams=2, receiver_type="mmse"
    )

    # Effective SNR should account for power penalty and diversity gain
    assert effective_snr_db < snr_siso_db  # Power split penalty
    assert effective_snr_db > snr_siso_db - 3  # But diversity gain recovers some
    assert metrics["num_streams_used"] == 2
```

#### Test 5: MIMO Rate Scaling

```python
def test_mimo_rate_scaling():
    """Verify rate scales with number of spatial streams."""
    rate_siso = PERCalculator.calculate_effective_rate(
        bandwidth_mhz=80,
        modulation_bits=6,  # 64-QAM
        code_rate=0.75,
        per=0.01,
        num_spatial_streams=1,
    )

    rate_2x2 = PERCalculator.calculate_effective_rate(
        bandwidth_mhz=80,
        modulation_bits=6,
        code_rate=0.75,
        per=0.01,
        num_spatial_streams=2,
    )

    # 2×2 should be ~2× rate (ideal case)
    assert rate_2x2 / rate_siso > 1.8
    assert rate_2x2 / rate_siso < 2.1
```

### Integration Tests

**Location**: `tests/integration/test_mimo_deployment.py` (new file)

#### Test 6: Full 2×2 MIMO Deployment

```python
@pytest.mark.integration
def test_mimo_2x2_deployment(project_root):
    """Test full deployment with 2×2 MIMO configuration."""

    # Create MIMO topology YAML
    topology_yaml = """
    name: mimo-test
    topology:
      scene:
        file: scenes/vacuum.xml
      nodes:
        node1:
          kind: linux
          image: alpine:latest
          interfaces:
            eth1:
              wireless:
                tx_antenna_array:
                  num_rows: 2
                  num_cols: 1
                  element_pattern: hw_dipole
                  polarization: V
                rx_antenna_array:
                  num_rows: 2
                  num_cols: 1
                  element_pattern: hw_dipole
                  polarization: V
                mimo_config:
                  num_spatial_streams: 2
                  receiver_type: mmse
                position: {x: 0, y: 0, z: 1}
                rf_power_dbm: 20.0
                frequency_ghz: 5.18
                bandwidth_mhz: 80
                mcs_table: examples/wifi6_mimo/wifi6_mcs_mimo.csv
        node2:
          kind: linux
          image: alpine:latest
          interfaces:
            eth1:
              wireless:
                tx_antenna_array:
                  num_rows: 2
                  num_cols: 1
                  element_pattern: hw_dipole
                  polarization: V
                rx_antenna_array:
                  num_rows: 2
                  num_cols: 1
                  element_pattern: hw_dipole
                  polarization: V
                mimo_config:
                  num_spatial_streams: 2
                  receiver_type: mmse
                position: {x: 20, y: 0, z: 1}
                rf_power_dbm: 20.0
                frequency_ghz: 5.18
                bandwidth_mhz: 80
                mcs_table: examples/wifi6_mimo/wifi6_mcs_mimo.csv
      links:
        - endpoints: [node1:eth1, node2:eth1]
    """

    # Write topology, deploy, verify rate is ~2× SISO
    # ... deployment logic ...
```

---

## Validation Criteria

### Expected Throughput Gains

| Scenario | Configuration | Expected Throughput vs. SISO | Test |
|----------|---------------|------------------------------|------|
| Free-space LOS | 2×2 MIMO | 1.0-1.2× (rank-1, diversity only) | Test 2 |
| Indoor multipath | 2×2 MIMO | 1.5-1.9× (partial multiplexing) | Test 3 |
| Rich scattering | 2×2 MIMO | 1.8-2.0× (ideal multiplexing) | Test 3 |
| Indoor multipath | 4×4 MIMO | 3.0-3.8× (partial multiplexing) | Integration |

### Key Metrics to Verify

1. **Channel Rank**: LOS = 1, indoor = 2, rich = min(num_tx, num_rx)
2. **Eigenvalue Spread**: LOS >10 dB gap, rich <5 dB gap
3. **Effective SNR**: Should account for power penalty (-3 dB for 2 streams) and diversity gain
4. **Rate Scaling**: Should NOT blindly double; depends on channel rank
5. **Backward Compatibility**: SISO configuration (1×1) should give identical results to current implementation

---

## Documentation Updates

### User-Facing Documentation

**Location**: `CLAUDE.md`

#### Add MIMO Section

```markdown
## MIMO (Multiple-Input Multiple-Output) Support

SiNE supports MIMO spatial multiplexing and diversity for WiFi 6 and 5G scenarios.

### Configuration

**MIMO Interface Example** (2×2 spatial multiplexing):
```yaml
interfaces:
  eth1:
    wireless:
      tx_antenna_array:
        num_rows: 2          # 2 TX antennas
        num_cols: 1
        vertical_spacing_wavelengths: 0.5  # λ/2 spacing
        element_pattern: hw_dipole
        polarization: V
      rx_antenna_array:
        num_rows: 2          # 2 RX antennas
        num_cols: 1
        vertical_spacing_wavelengths: 0.5
        element_pattern: hw_dipole
        polarization: V
      mimo_config:
        num_spatial_streams: 2
        receiver_type: mmse
      # ... rest of wireless params ...
```

### MIMO Modes

| Mode | Config | Use Case | Expected Gain |
|------|--------|----------|---------------|
| **Diversity (MRC)** | `receiver_type: mrc`, `num_spatial_streams: 1` | Reliability over throughput | +3 dB SNR (2×2) |
| **Spatial Multiplexing** | `receiver_type: mmse`, `num_spatial_streams: 2` | Throughput over reliability | 1.5-2× rate (2×2) |

### Throughput Expectations

- **LOS (rank-1)**: Minimal multiplexing gain, ~1.2× vs SISO
- **Indoor (rank-2)**: Partial multiplexing, ~1.7× vs SISO
- **Rich scattering**: Full multiplexing, ~2× vs SISO (2×2)
```

### API Documentation

**Location**: Update channel server API docs

- Document MIMO request parameters
- Add MIMO response fields (eigenvalues, rank, condition number)
- Provide example MIMO API calls

---

## Migration Path

### Backward Compatibility

**Guaranteed**: Existing SISO topologies continue to work unchanged
- `antenna_pattern: hw_dipole` → defaults to 1×1 array (SISO)
- `antenna_gain_dbi: 3.0` → SISO explicit gain
- No MIMO fields → SISO code path

### Gradual Adoption

1. **Phase 1-2**: Internal MIMO engine available, but users continue using SISO configs
2. **Phase 3**: Add MIMO examples to `examples/mimo_2x2/` directory
3. **Phase 4**: Document MIMO in user guide and tutorials
4. **Phase 5**: Update adaptive MCS examples to showcase MIMO gains

---

## Critical Files Summary

### Modified Files

| File | Changes | Lines Affected |
|------|---------|----------------|
| `src/sine/config/schema.py` | Add `AntennaArrayConfig`, `MIMOConfig`, extend `WirelessParams`, update validation | +150 lines |
| `src/sine/channel/sionna_engine.py` | Add MIMO array params to `add_transmitter/receiver()`, new `compute_mimo_channel_matrix()` | +250 lines |
| `src/sine/channel/snr.py` | Add `calculate_mimo_effective_snr()` method | +100 lines |
| `src/sine/channel/per_calculator.py` | Add `num_spatial_streams` parameter to `calculate_effective_rate()` | +5 lines |
| `src/sine/channel/server.py` | Extend request/response models, modify `compute_channel_for_link()` for MIMO | +200 lines |
| `src/sine/channel/modulation.py` | Extend `select_mcs()` to filter by num_streams (Phase 6) | +20 lines |

### New Files

| File | Purpose |
|------|---------|
| `tests/channel/test_mimo_channel.py` | Unit tests for MIMO channel matrix extraction |
| `tests/channel/test_mimo_snr.py` | Unit tests for MIMO effective SNR calculation |
| `tests/integration/test_mimo_deployment.py` | Integration tests for full MIMO deployment |
| `examples/mimo_2x2/network.yaml` | 2×2 MIMO example topology |
| `examples/wifi6_mimo/wifi6_mcs_mimo.csv` | WiFi 6 MCS table with spatial streams |

---

## Rollout Plan

### Iteration 1: Core MIMO Engine (Phase 1-3)
- **Duration**: ~1 week
- **Deliverables**: Schema, MIMO channel matrix, effective SNR
- **Validation**: Unit tests (Tests 1-4)

### Iteration 2: Rate Scaling and Server Integration (Phase 4-5)
- **Duration**: ~3 days
- **Deliverables**: Rate calculation, server API wiring
- **Validation**: Integration test (Test 6)

### Iteration 3: MCS Tables and Documentation (Phase 6)
- **Duration**: ~2 days
- **Deliverables**: MIMO MCS tables, documentation, examples
- **Validation**: End-to-end deployment test

---

## Open Questions for User

1. **Phasing preference**: Should we implement all phases at once, or iteratively (Phase 1-2 first, then 3-5)?

2. **Antenna array dimensionality**: Focus on linear arrays (1×N) or support 2D planar arrays (M×N)?
   - Linear (simpler): `num_antenna_rows=2, num_cols=1`
   - Planar (future): `num_rows=2, num_cols=2` for 4×4 MIMO

3. **MCS table format**: Reuse existing MCS tables with automatic stream scaling, or require separate MIMO MCS tables?

4. **Fallback engine**: Should fallback engine (FSPL) support MIMO, or MIMO-only with Sionna RT?
   - Recommendation: MIMO requires Sionna RT (eigenvalue computation from spatial channel)

5. **SINR with MIMO**: For multi-node interference scenarios, implement scalar SINR (Phase 1-3) or full MIMO interference matrices (Phase 5)?
   - Recommendation: Start with scalar SINR, upgrade later if needed

---

## Success Metrics

- ✅ Schema validation passes for MIMO config
- ✅ 2×2 MIMO in LOS shows rank-1 (expected behavior)
- ✅ 2×2 MIMO in indoor shows rank-2 with ~1.7× throughput vs SISO
- ✅ SISO configs unchanged and give identical results
- ✅ Integration test deploys MIMO topology successfully
- ✅ Documentation complete with examples

---

**End of Plan**
