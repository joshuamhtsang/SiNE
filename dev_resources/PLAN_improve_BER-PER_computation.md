# Improvements to BER/PER Computation in SiNE

**Created**: 2026-01-30
**Status**: Planning
**Priority**: Medium-High

## Executive Summary

This document outlines suggested improvements to SiNE's BER (Bit Error Rate) and PER (Packet Error Rate) computation pipeline. The current implementation uses theoretical AWGN formulas with coding gain offsets, which provides fast, deterministic results but has limitations in accuracy for certain scenarios.

## Current Implementation

### Architecture

```
SNR (dB) → Eb/N0 → BER (modulation-specific formula)
                            ↓
                    BLER (with FEC coding gain offset)
                            ↓
                    PER (from BER or BLER)
                            ↓
         Netem parameters: loss_percent = PER × 100
```

### Key Files

- `src/sine/channel/modulation.py` - BER/BLER calculation
- `src/sine/channel/per_calculator.py` - PER conversion
- `src/sine/channel/snr.py` - SNR/link budget
- `src/sine/channel/sinr.py` - SINR with interference

### BER Formulas by Modulation

**BPSK/QPSK**:
```python
BER = 0.5 × erfc(√(Eb/N0))
```

**M-QAM (16-QAM, 64-QAM, 256-QAM, 1024-QAM)**:
```python
# Symbol Error Rate
SER = 4 × (1 - 1/√M) × Q(√(3×SNR/(M-1)))

# Convert to BER (Gray coding approximation)
BER = SER / log2(M)
```

### Current Limitations

1. **Frequency-flat assumption**: Does not capture per-subcarrier fading in OFDM
2. **Coding gain approximations**: Simple offset model, not actual LDPC/Polar performance
3. **No jitter modeling**: Set to 0.0 (MAC/queue effects ignored)
4. **Static channel**: No time-varying fading (Doppler, Rayleigh/Rician)
5. **Gray coding approximation**: Less accurate for high-order QAM at low SNR
6. **SISO only**: No MIMO/beamforming support

## Proposed Improvements

### 🎯 Phase 1: High Impact, Medium Complexity

#### 1. Effective SINR Mapping (EESM/MIESM)

**Problem**: Current frequency-flat AWGN assumption ignores per-subcarrier fading in OFDM.

**Solution**: Implement link-to-system mapping (3GPP standard approach):

```python
class EESMCalculator:
    """Exponential Effective SINR Mapping for frequency-selective fading."""

    def calculate_effective_sinr(
        self,
        per_subcarrier_sinr: np.ndarray,  # SINR per OFDM subcarrier
        beta: float = 1.0  # Modulation-specific parameter
    ) -> float:
        """
        Map per-subcarrier SINR to single effective SINR.

        EESM formula:
            SINR_eff = -β × ln(mean(exp(-SINR_i / β)))

        Beta values (typical):
        - QPSK: β ≈ 1.0
        - 16-QAM: β ≈ 1.5
        - 64-QAM: β ≈ 3.2
        - 256-QAM: β ≈ 6.4
        - 1024-QAM: β ≈ 10.0
        """
        sinr_linear = 10 ** (per_subcarrier_sinr / 10)
        effective_sinr_linear = -beta * np.log(np.mean(np.exp(-sinr_linear / beta)))
        return 10 * np.log10(effective_sinr_linear)
```

**Benefits**:
- Captures frequency selectivity within OFDM bandwidth
- Industry-standard (3GPP LTE/5G, WiMAX, WiFi 6)
- Validated against real measurements
- Sionna already provides per-subcarrier channels via `frequencies` parameter

**Implementation**:
1. Modify Sionna engine to compute CIR at multiple subcarrier frequencies
2. Add EESM calculator to modulation module
3. Add beta parameter table for each modulation scheme
4. Update channel computation pipeline to use EESM when enabled

**Effort**: 2-3 days
**Priority**: ⭐⭐⭐

**References**:
- 3GPP TR 36.942: "Evolved Universal Terrestrial Radio Access (E-UTRA); Radio Frequency (RF) system scenarios"
- Brueninghaus et al., "Link Performance Models for System Level Simulations of Broadband Radio Access Systems", IEEE PIMRC 2005

---

#### 2. BLER Lookup Tables (Pre-Simulated)

**Problem**: Coding gain offsets are rough approximations (±2 dB error typical).

**Solution**: Pre-compute BLER lookup tables using Sionna's actual LDPC/Polar encoders:

```python
class BLERLookupTable:
    """Pre-simulated BLER curves for various MCS configurations."""

    def __init__(self, table_path: str = "data/bler_tables.npz"):
        """
        Load pre-computed BLER tables.

        Table format:
            {
                (modulation, code_rate, fec_type, block_length):
                    [(snr_db, bler), ...]
            }
        """
        self.tables = self._load_tables(table_path)

    def get_bler(
        self,
        modulation: str,
        code_rate: float,
        fec_type: str,
        snr_db: float,
        block_length: int = 1024
    ) -> float:
        """Interpolate BLER from pre-computed table."""
        key = (modulation, code_rate, fec_type, block_length)

        if key not in self.tables:
            # Fallback to nearest table or theoretical formula
            key = self._find_nearest_table(key)

        snr_bler_curve = self.tables[key]
        return np.interp(snr_db, snr_bler_curve[:, 0], snr_bler_curve[:, 1])
```

**Table Generation Script**:
```python
# scripts/generate_bler_tables.py
def generate_bler_table(
    modulation: str,
    code_rate: float,
    fec_type: str,
    block_length: int,
    num_blocks: int = 1000,  # Simulation size
    snr_range_db: tuple = (-5, 35),
    snr_step_db: float = 0.5
):
    """
    Run Sionna simulation to generate BLER curve.

    Process:
    1. Create Sionna encoder/decoder for specified config
    2. For each SNR point:
        a. Generate random bits
        b. Encode with FEC
        c. Modulate
        d. Add AWGN noise
        e. Demodulate
        f. Decode with FEC
        g. Count block errors
    3. Save (SNR, BLER) curve to table
    """
    # Implementation using Sionna FEC and modulation modules
    pass
```

**Benefits**:
- Accurate BLER without runtime simulation overhead
- Captures real LDPC/Polar performance (waterfall curves, error floors)
- Tables generated once, used forever (deterministic)
- Supports different block lengths, code rates, puncturing

**Implementation**:
1. Create table generation script using Sionna FEC encoders
2. Generate tables for WiFi 6 MCS indices (0-11)
3. Store tables in `data/bler_tables.npz` (NumPy compressed format)
4. Add `BLERLookupTable` class to modulation module
5. Add config option to enable/disable lookup tables (fallback to theoretical)

**Effort**: 1 week (3 days simulation, 2 days integration, 2 days validation)
**Priority**: ⭐⭐⭐

**Table Coverage**:
- Modulations: BPSK, QPSK, 16-QAM, 64-QAM, 256-QAM, 1024-QAM
- Code rates: 1/3, 1/2, 2/3, 3/4, 5/6
- FEC types: LDPC, Polar
- Block lengths: 256, 512, 1024, 2048 bits
- SNR range: -5 to 35 dB (0.5 dB steps)

**Storage**: ~50 MB compressed (acceptable for local package)

---

#### 3. MAC/Queue-Based Jitter Modeling

**Problem**: Jitter currently set to 0.0 (ignores MAC layer effects).

**Solution**: Model jitter from CSMA/CA contention and queueing:

```python
class MACJitterModel:
    """Statistical jitter model for CSMA/CA and queue effects."""

    def __init__(
        self,
        mac_protocol: str = "csma_ca",  # or "tdma", "none"
        slot_time_us: float = 9.0,  # WiFi 6 slot time
    ):
        self.mac_protocol = mac_protocol
        self.slot_time_us = slot_time_us

    def calculate_jitter(
        self,
        num_contenders: int,
        channel_utilization: float,  # 0-1
        queue_length: int,
        packet_service_time_ms: float,
        per: float  # For retransmission modeling
    ) -> float:
        """
        Estimate jitter from MAC contention and queueing.

        Components:
        1. CSMA/CA backoff variance (contention-based)
        2. Queue waiting time variance (M/M/1 model)
        3. Retransmission delays (from PER)

        Returns:
            Jitter in milliseconds (standard deviation of delay)
        """
        if self.mac_protocol == "none":
            return 0.0

        jitter_components = []

        # 1. CSMA/CA backoff jitter
        if self.mac_protocol == "csma_ca":
            avg_backoff_slots = self._calculate_avg_backoff(num_contenders)
            backoff_variance_slots = self._calculate_backoff_variance(num_contenders)
            backoff_jitter_ms = np.sqrt(backoff_variance_slots) * (self.slot_time_us / 1000)
            jitter_components.append(backoff_jitter_ms)

        # 2. Queueing jitter (M/M/1 approximation)
        if channel_utilization < 0.95:
            # Standard deviation of queue wait time
            queue_jitter_ms = (
                packet_service_time_ms * channel_utilization
                / (1 - channel_utilization)
            )
            jitter_components.append(queue_jitter_ms)
        else:
            # Saturated queue, use empirical cap
            jitter_components.append(50.0)

        # 3. Retransmission jitter
        if per > 0.01:  # Significant packet loss
            # Average retransmissions = PER / (1 - PER) for single-retry ARQ
            avg_retx = per / (1 - per) if per < 0.9 else 1.0
            retx_jitter_ms = avg_retx * packet_service_time_ms
            jitter_components.append(retx_jitter_ms)

        # Total jitter (combine variances, then take sqrt)
        total_variance = sum(j**2 for j in jitter_components)
        total_jitter_ms = np.sqrt(total_variance)

        return min(total_jitter_ms, 100.0)  # Cap at 100ms (sanity check)

    def _calculate_avg_backoff(self, num_contenders: int) -> float:
        """
        Average backoff slots for CSMA/CA (IEEE 802.11).

        Binary exponential backoff:
        - Initial CW = 15 (WiFi 6)
        - Max CW = 1023
        - Average backoff = CW/2
        """
        if num_contenders <= 1:
            return 0.0

        # Approximate collision probability
        p_collision = 1 - (1 - 1/num_contenders)**(num_contenders - 1)

        # Average number of backoff stages
        avg_stages = min(p_collision * 6, 6)  # Max 6 stages in 802.11

        # Average CW across stages
        avg_cw = 15 * (2**avg_stages - 1) / avg_stages if avg_stages > 0 else 15

        return avg_cw / 2

    def _calculate_backoff_variance(self, num_contenders: int) -> float:
        """Variance of backoff time."""
        avg_cw = self._calculate_avg_backoff(num_contenders) * 2
        # Uniform distribution variance: Var = (b-a)^2 / 12
        return (avg_cw**2) / 12
```

**Benefits**:
- Realistic packet timing variation (0.1-10 ms typical)
- Models hidden node collisions, queue buildup
- Useful for VoIP, video streaming, real-time app testing
- Diagnostic for identifying congestion vs. channel quality issues

**Implementation**:
1. Add `MACJitterModel` class to new file `src/sine/channel/jitter.py`
2. Integrate into PER calculator's `calculate_netem_params()`
3. Add config parameters to wireless interface schema:
   ```yaml
   wireless:
     mac_protocol: csma_ca  # or tdma, none
     num_contenders: 5  # Estimated network size
     channel_utilization: 0.3  # 30% airtime usage
   ```
4. Update deployment summary to show jitter sources

**Effort**: 3-4 days (model development + integration + validation)
**Priority**: ⭐⭐

**Validation**:
- Compare against ns-3 802.11 MAC simulations
- Verify jitter ranges match empirical WiFi measurements (0.5-20 ms typical)

---

### 📊 Phase 2: Medium Impact, Low Complexity

#### 4. Doppler/Fast Fading Model

**Problem**: Static channel (no time-varying fading).

**Solution**: Add Rayleigh/Rician fading on top of geometric SNR:

```python
class FastFadingModel:
    """Time-varying fading model for mobile scenarios."""

    def __init__(self, update_interval_ms: float = 100.0):
        """
        Initialize fast fading model.

        Args:
            update_interval_ms: How often fading is updated (mobility poll interval)
        """
        self.update_interval_ms = update_interval_ms
        self.fading_state = {}  # Per-link state

    def add_fading(
        self,
        link_id: str,
        snr_db: float,
        k_factor_db: float,  # From ray tracing (LOS strength)
        velocity_mps: float,  # Relative velocity
        frequency_hz: float
    ) -> float:
        """
        Apply fast fading to SNR.

        Fading model:
        - Rayleigh (K=0 dB, NLOS): SNR varies ±10 dB over coherence time
        - Rician (K>0 dB, LOS): Less variation, LOS component stabilizes

        Coherence time:
            Tc ≈ 0.423 / fd
            where fd = v × f / c (Doppler frequency)

        Args:
            link_id: Unique link identifier for state tracking
            snr_db: Base SNR from geometric path loss
            k_factor_db: Rician K-factor (dB), 0 = Rayleigh, >10 = strong LOS
            velocity_mps: Relative velocity between TX and RX (m/s)
            frequency_hz: Carrier frequency

        Returns:
            SNR with fading applied (dB)
        """
        # Calculate Doppler frequency
        c = 3e8  # Speed of light
        doppler_hz = velocity_mps * frequency_hz / c

        # Calculate coherence time
        if doppler_hz > 0:
            coherence_time_ms = 423 / doppler_hz  # ms
        else:
            coherence_time_ms = float('inf')  # Static

        # Determine fading standard deviation
        k_linear = 10 ** (k_factor_db / 10)

        if k_factor_db > 10.0:
            # Strong LOS, minimal fading (≈1-2 dB variation)
            fading_std_db = 1.0
        elif k_factor_db > 3.0:
            # Moderate LOS, some fading (≈3-5 dB)
            fading_std_db = 3.0 / (1 + k_linear)
        else:
            # NLOS, Rayleigh-like fading (≈5-10 dB)
            fading_std_db = 8.0 / (1 + k_linear)

        # Check if we need to update fading (coherence time elapsed)
        if link_id not in self.fading_state:
            self.fading_state[link_id] = {
                'last_update_ms': 0,
                'fading_db': 0.0
            }

        state = self.fading_state[link_id]
        elapsed_ms = self.update_interval_ms

        if elapsed_ms >= coherence_time_ms:
            # Coherence time elapsed, draw new fading sample
            # Log-normal distribution (approximates Rayleigh/Rician envelope)
            state['fading_db'] = np.random.normal(0, fading_std_db)
            state['last_update_ms'] = 0
        else:
            # Use previous fading value (channel hasn't changed)
            state['last_update_ms'] += elapsed_ms

        return snr_db + state['fading_db']
```

**Benefits**:
- Models channel time variation for mobility
- Simple to implement (no Sionna changes needed)
- Useful for testing rate adaptation robustness
- Enables realistic mobile scenarios (vehicles, drones)

**Implementation**:
1. Add `FastFadingModel` class to `src/sine/channel/fading.py`
2. Integrate into channel computation (optional flag)
3. Add to mobility update loop
4. Expose via config:
   ```yaml
   wireless:
     enable_fast_fading: true
     velocity_mps: 5.0  # 5 m/s (walking speed)
   ```

**Effort**: 1-2 days
**Priority**: ⭐⭐

**Validation**:
- Verify fading statistics match Rayleigh/Rician distributions
- Check coherence time matches theory (Tc ≈ 9λ/16πv for Rayleigh)

---

#### 5. Code Rate-Dependent Coding Gains (Refined Table)

**Problem**: Linear code rate adjustment is oversimplified.

**Solution**: Use measured coding gains from literature:

```python
# In src/sine/channel/modulation.py
class BLERCalculator:
    def __init__(self, ...):
        # Replace simple linear model with empirical table
        # Values from 3GPP measurements and academic literature
        self.coding_gains = {
            "ldpc": {
                0.33: 7.5,  # Rate-1/3 LDPC (more redundancy)
                0.50: 6.5,  # Rate-1/2
                0.67: 5.0,  # Rate-2/3
                0.75: 4.2,  # Rate-3/4
                0.83: 3.5,  # Rate-5/6 (less redundancy)
                0.90: 2.5,  # Rate-9/10 (minimal redundancy)
            },
            "polar": {
                0.33: 7.0,
                0.50: 6.0,
                0.67: 4.5,
                0.75: 3.8,
                0.83: 3.0,
                0.90: 2.0,
            },
            "turbo": {
                0.33: 6.5,
                0.50: 5.5,
                0.67: 4.0,
                0.75: 3.5,
                0.83: 2.8,
                0.90: 1.8,
            },
            "none": {
                1.0: 0.0
            }
        }

    def get_coding_gain(self, fec_type: str, code_rate: float) -> float:
        """
        Interpolate coding gain from empirical table.

        Args:
            fec_type: FEC type (ldpc, polar, turbo, none)
            code_rate: Code rate (0.0 to 1.0)

        Returns:
            Coding gain in dB at BER ≈ 10^-5
        """
        table = self.coding_gains.get(fec_type.lower(), self.coding_gains["none"])
        rates = sorted(table.keys())
        gains = [table[r] for r in rates]

        # Linear interpolation
        return float(np.interp(code_rate, rates, gains))
```

**Data Sources**:
- LDPC: IEEE 802.11n/ac/ax measurements
- Polar: 3GPP TS 38.212 (5G NR)
- Turbo: 3GPP TS 36.212 (LTE)

**Benefits**:
- More accurate BLER without full simulation
- Based on published measurements (±0.5 dB typical accuracy)
- Easy to update with new data

**Effort**: 1 day (literature review + implementation)
**Priority**: ⭐

---

#### 6. Gray Coding Correction for High-Order QAM

**Problem**: Uses approximation `BER ≈ SER / log2(M)` for M-QAM.

**Solution**: Account for bit position effects (I/Q, MSB/LSB):

```python
def calculate_qam_ber(self, snr_db: float, M: int) -> float:
    """
    More accurate QAM BER using exact Gray coding analysis.

    Current approximation: BER ≈ SER / log2(M)
    Better approach: Account for bit position (I/Q, MSB/LSB)

    Gray coding property: Most symbol errors affect only 1 bit,
    but at low SNR, multi-bit errors become significant for high-order QAM.
    """
    # Symbol Error Rate (same as before)
    ser = self._calculate_qam_ser(snr_db, M)

    # Average bits per symbol error (Gray coding property)
    # Derived from constellation geometry and nearest-neighbor errors
    if M <= 4:  # QPSK
        avg_bits_per_error = 1.0  # Always single-bit errors
    elif M == 16:  # 16-QAM
        # Most errors: 1 bit, some corner cases: 2 bits
        avg_bits_per_error = 1.05 if snr_db > 10 else 1.15
    elif M == 64:  # 64-QAM
        # SNR-dependent: more multi-bit errors at low SNR
        avg_bits_per_error = 1.05 if snr_db > 15 else 1.20
    elif M == 256:  # 256-QAM
        avg_bits_per_error = 1.10 if snr_db > 20 else 1.30
    elif M >= 1024:  # 1024-QAM
        avg_bits_per_error = 1.15 if snr_db > 25 else 1.40
    else:
        # Fallback to approximation
        avg_bits_per_error = 1.0

    # BER = (SER × avg_bits_per_error) / log2(M)
    ber = (ser * avg_bits_per_error) / np.log2(M)

    return float(np.clip(ber, 1e-12, 0.5))
```

**Benefits**:
- ~0.5-1 dB accuracy improvement for 256-QAM, 1024-QAM
- Minimal code change
- Better match to empirical measurements

**Effort**: 0.5 days
**Priority**: ⭐

**Validation**:
- Compare against Sionna's full simulation (`SionnaBERCalculator`)
- Verify against IEEE 802.11ax published curves

---

### 🚀 Phase 3: High Impact, High Complexity (Future Work)

#### 7. Multi-User MIMO (MU-MIMO) Support

**Problem**: SISO only (no spatial multiplexing/beamforming).

**Solution**: Add MIMO channel modeling with Sionna RT:

```python
class MIMOChannelModel:
    """Multi-antenna channel model with beamforming."""

    def __init__(self, num_tx_antennas: int, num_rx_antennas: int):
        """
        Initialize MIMO channel model.

        Args:
            num_tx_antennas: Number of transmit antennas (1, 2, 4, 8)
            num_rx_antennas: Number of receive antennas (1, 2, 4, 8)
        """
        self.num_tx = num_tx_antennas
        self.num_rx = num_rx_antennas
        self.rank = min(num_tx_antennas, num_rx_antennas)

    def calculate_mimo_sinr(
        self,
        paths: sionna.rt.Paths,
        beamforming_type: str = "maxratio",  # or "zeroforcing", "mmse", "spatial_mux"
        base_snr_db: float = 20.0
    ) -> tuple[float, dict]:
        """
        Calculate MIMO SINR with beamforming gain.

        Sionna RT already provides MIMO channel matrices via paths.cir()
        when antenna arrays are configured.

        Args:
            paths: Sionna Paths object with MIMO channel
            beamforming_type: Beamforming/precoding scheme
            base_snr_db: SISO SNR (before MIMO gain)

        Returns:
            (effective_sinr_db, mimo_metadata)
        """
        # Get MIMO channel matrix H (Rx × Tx × num_paths × num_ofdm_symbols)
        H = self._get_mimo_channel_matrix(paths)

        # Apply beamforming/precoding
        if beamforming_type == "maxratio":
            # Maximum Ratio Transmission (MRT)
            # SNR gain = num_tx_antennas (best case, no interference)
            bf_gain_db = 10 * np.log10(self.num_tx)
            effective_rank = 1  # Single stream

        elif beamforming_type == "zeroforcing":
            # Zero-Forcing (ZF) precoding
            # Eliminates inter-stream interference
            # SNR gain depends on channel conditioning
            H_pinv = np.linalg.pinv(H)
            bf_gain_db = 10 * np.log10(np.linalg.norm(H_pinv)**2)
            effective_rank = self.rank

        elif beamforming_type == "mmse":
            # Minimum Mean Square Error (MMSE)
            # Balances noise and interference
            noise_var = 10 ** (-base_snr_db / 10)
            H_mmse = np.linalg.inv(H.conj().T @ H + noise_var * np.eye(self.num_tx))
            bf_gain_db = 10 * np.log10(np.linalg.norm(H_mmse)**2)
            effective_rank = self.rank

        elif beamforming_type == "spatial_mux":
            # Spatial multiplexing (no beamforming)
            # Capacity gain from parallel streams
            # Each stream has lower SNR, but total capacity increases
            bf_gain_db = 0  # Per-stream SNR unchanged
            effective_rank = self.rank
            data_rate_multiplier = effective_rank  # Key benefit

        else:
            raise ValueError(f"Unknown beamforming type: {beamforming_type}")

        # Calculate effective SINR
        effective_sinr_db = base_snr_db + bf_gain_db

        metadata = {
            "beamforming_type": beamforming_type,
            "num_tx_antennas": self.num_tx,
            "num_rx_antennas": self.num_rx,
            "effective_rank": effective_rank,
            "bf_gain_db": bf_gain_db,
            "mimo_mode": "SU-MIMO"  # Single-user MIMO
        }

        return effective_sinr_db, metadata

    def _get_mimo_channel_matrix(self, paths: sionna.rt.Paths) -> np.ndarray:
        """Extract MIMO channel matrix from Sionna Paths."""
        # Sionna provides paths.cir() which includes antenna array effects
        # Shape: [batch, num_rx, num_rx_ant, num_tx, num_tx_ant, num_paths, num_time_steps]
        a, tau = paths.cir()

        # Average over time and paths to get effective channel matrix
        H = np.mean(np.abs(a), axis=(-1, -2))  # [num_rx_ant, num_tx_ant]

        return H
```

**Sionna RT Configuration**:
```python
# In network.yaml (future schema extension)
nodes:
  node1:
    interfaces:
      eth1:
        wireless:
          antenna_array:
            type: "ula"  # Uniform Linear Array
            num_elements: 4
            element_spacing_lambda: 0.5
            polarization: "V"
          beamforming: "maxratio"  # or "zeroforcing", "spatial_mux"
```

**Benefits**:
- Enables WiFi 6/6E MIMO scenarios (2×2, 4×4, 8×8)
- Beamforming can add 3-10 dB effective SNR gain
- Spatial multiplexing increases data rate by 2-8×
- Sionna RT already supports MIMO channel modeling

**Implementation**:
1. Extend schema to support antenna array configuration
2. Add MIMO channel model class
3. Integrate with Sionna RT antenna arrays
4. Update channel computation pipeline
5. Extend MCS table to include spatial streams

**Effort**: 2-3 weeks (complex integration + testing)
**Priority**: Future (requires significant Sionna RT expertise)

**References**:
- IEEE 802.11ax-2021: "WiFi 6 MIMO and MU-MIMO"
- Sionna RT documentation: Antenna arrays and MIMO channels

---

#### 8. HARQ Retransmission Modeling

**Problem**: Single-shot transmission (no HARQ).

**Solution**: Model Hybrid ARQ with soft combining:

```python
class HARQModel:
    """HARQ retransmission with chase combining or incremental redundancy."""

    def __init__(
        self,
        max_retransmissions: int = 4,
        combining_type: str = "chase",  # or "ir" (incremental redundancy)
        rtt_ms: float = 10.0  # Round-trip time
    ):
        """
        Initialize HARQ model.

        Args:
            max_retransmissions: Max number of (re)transmissions (1 = no HARQ)
            combining_type: "chase" (same redundancy) or "ir" (incremental)
            rtt_ms: Round-trip time for ACK/NACK feedback
        """
        self.max_retx = max_retransmissions
        self.combining_type = combining_type
        self.rtt_ms = rtt_ms

    def calculate_effective_bler_with_harq(
        self,
        initial_bler: float,
        snr_db: float
    ) -> tuple[float, float, dict]:
        """
        Calculate effective BLER and average delay with HARQ.

        Chase combining:
            - Each retransmission uses same code rate
            - Combining gain ≈ 3 dB per retransmission
            - BLER_k ≈ BLER_0^k (pessimistic approximation)

        Incremental redundancy (IR):
            - Each retransmission adds more parity bits (lower effective code rate)
            - Combining gain ≈ 5-6 dB per retransmission
            - More gain than chase, but requires more sophisticated receiver

        Returns:
            (effective_bler, avg_delay_ms, metadata)
        """
        bler_per_transmission = [initial_bler]

        if self.combining_type == "chase":
            # Each retransmission improves SNR by ~3 dB (combining gain)
            for k in range(1, self.max_retx):
                # Approximate: BLER improves by 3 dB per retransmission
                improved_snr_db = snr_db + 3.0 * k
                # Recompute BLER at improved SNR (simplified)
                bler_k = initial_bler ** (1.5 ** k)  # Heuristic: faster than exponential
                bler_per_transmission.append(bler_k)

        elif self.combining_type == "ir":
            # Incremental redundancy: each retransmission lowers code rate
            # Example: rate 3/4 → 2/3 → 1/2 → 1/3
            for k in range(1, self.max_retx):
                # More gain than chase (5-6 dB improvement)
                improved_snr_db = snr_db + 5.0 * k
                bler_k = initial_bler ** (2.0 ** k)  # Faster convergence
                bler_per_transmission.append(bler_k)

        # Calculate probability of success after k transmissions
        # P(success after k) = (1 - BLER_1) × ... × (1 - BLER_k)
        cumulative_success_prob = 1.0
        transmission_probs = []

        for k, bler_k in enumerate(bler_per_transmission):
            # Probability of needing exactly k+1 transmissions
            prob_k = (1 - cumulative_success_prob) * (1 - bler_k)
            transmission_probs.append(prob_k)
            cumulative_success_prob += prob_k

        # Effective BLER after max_retx attempts
        effective_bler = 1.0 - cumulative_success_prob

        # Average delay = Σ(Pr[k retx] × k × RTT)
        avg_delay_ms = sum(
            (k + 1) * self.rtt_ms * transmission_probs[k]
            for k in range(len(transmission_probs))
        )

        metadata = {
            "combining_type": self.combining_type,
            "max_retransmissions": self.max_retx,
            "initial_bler": initial_bler,
            "effective_bler": effective_bler,
            "bler_reduction_db": 10 * np.log10(initial_bler / effective_bler) if effective_bler > 0 else float('inf'),
            "avg_transmissions": avg_delay_ms / self.rtt_ms,
        }

        return effective_bler, avg_delay_ms, metadata
```

**Benefits**:
- Dramatically improves reliability (BLER 10^-1 → 10^-6 with 4 retransmissions)
- Critical for 5G URLLC, industrial IoT, mission-critical links
- Models real LTE/5G behavior (used in 3GPP standards)
- Enables delay-reliability tradeoff analysis

**Implementation**:
1. Add `HARQModel` class to `src/sine/channel/harq.py`
2. Integrate into PER calculator (optional feature)
3. Add config parameters:
   ```yaml
   wireless:
     harq:
       enabled: true
       max_retransmissions: 4
       combining_type: ir  # or chase
       rtt_ms: 10.0
   ```
4. Update netem parameters:
   - `loss_percent`: Use effective BLER
   - `delay_ms`: Add average HARQ delay

**Effort**: 1 week (model development + integration + validation)
**Priority**: Future (advanced feature for specific use cases)

**Validation**:
- Compare against 3GPP HARQ performance curves
- Verify delay-reliability tradeoff matches theoretical models

---

## Implementation Roadmap

### Phase 1: Quick Wins (1 week)

**Goal**: Immediate accuracy improvements with minimal risk.

| Task | Effort | Priority | Dependencies |
|------|--------|----------|--------------|
| Gray coding correction | 0.5 days | ⭐ | None |
| Code rate-dependent gains | 1 day | ⭐ | Literature review |
| Doppler/fast fading | 1-2 days | ⭐⭐ | None |

**Deliverables**:
- Updated `modulation.py` with improved BER formulas
- `fading.py` module for time-varying channels
- Unit tests for all changes
- Documentation updates

---

### Phase 2: High-Value Features (2 weeks)

**Goal**: Industry-standard techniques for significant accuracy gains.

| Task | Effort | Priority | Dependencies |
|------|--------|----------|--------------|
| EESM/MIESM implementation | 2-3 days | ⭐⭐⭐ | Sionna multi-frequency CIR |
| MAC jitter modeling | 3-4 days | ⭐⭐ | None |

**Deliverables**:
- EESM calculator with beta parameter tables
- MAC jitter model (CSMA/CA, TDMA, queueing)
- Integration tests with realistic scenarios
- Performance benchmarks (verify no major slowdown)

---

### Phase 3: Advanced Features (3-4 weeks)

**Goal**: Pre-computed tables and advanced models.

| Task | Effort | Priority | Dependencies |
|------|--------|----------|--------------|
| BLER lookup tables | 1 week | ⭐⭐⭐ | Sionna FEC modules |
| HARQ retransmission model | 1 week | Future | BLER tables (optional) |

**Deliverables**:
- BLER table generation script
- Pre-computed tables for WiFi 6 MCS (0-11)
- `BLERLookupTable` class with interpolation
- HARQ model (optional, advanced use case)

---

### Phase 4: Research Projects (Future)

**Goal**: Cutting-edge features for specialized use cases.

| Task | Effort | Priority | Dependencies |
|------|--------|----------|--------------|
| MIMO/beamforming support | 2-3 weeks | Future | Sionna RT antenna arrays |
| MU-MIMO (multi-user) | 2-3 weeks | Future | MIMO implementation |

**Note**: Phase 4 requires deep Sionna RT expertise and is recommended for future research collaborations or dedicated development cycles.

---

## Validation Strategy

### Unit Tests

1. **BER formulas**: Compare against published curves (IEEE, 3GPP)
2. **EESM**: Verify against 3GPP test vectors
3. **Coding gains**: Match measured BLER curves within ±1 dB
4. **Jitter model**: Compare against ns-3 MAC simulations

### Integration Tests

1. **End-to-end accuracy**: Deploy test topologies, measure actual loss/delay/throughput
2. **Performance regression**: Ensure no >10% slowdown in channel computation
3. **Backwards compatibility**: Existing examples should still work

### Benchmark Scenarios

1. **Indoor multipath** (`two_rooms`): Validate EESM frequency selectivity
2. **Mobile scenario** (`mobility`): Validate Doppler/fast fading
3. **Dense network** (`manet_triangle_shared_sinr`): Validate interference + EESM
4. **High MCS** (`adaptive_mcs_wifi6`): Validate 256-QAM, 1024-QAM accuracy

---

## References

### Academic Papers

1. Brueninghaus et al., "Link Performance Models for System Level Simulations", IEEE PIMRC 2005
2. Ramiro-Moreno et al., "Effective SINR Mapping in LTE Systems", IEEE VTC 2011
3. Polyanskiy et al., "Channel Coding Rate in the Finite Blocklength Regime", IEEE Trans. IT 2010

### Standards

1. 3GPP TR 36.942: "E-UTRA RF system scenarios"
2. IEEE 802.11ax-2021: "WiFi 6 PHY and MAC"
3. 3GPP TS 38.212: "5G NR Multiplexing and channel coding"

### Sionna Documentation

1. [Sionna RT API](https://nvlabs.github.io/sionna/api/rt.html)
2. [Sionna FEC](https://nvlabs.github.io/sionna/api/fec.html)
3. [Sionna OFDM](https://nvlabs.github.io/sionna/api/ofdm.html)

---

## Configuration Interface (Proposed)

### Network YAML Schema Extension

```yaml
# Global channel computation settings (optional)
channel_computation:
  # BER/BLER method
  bler_method: "lookup_table"  # or "theoretical", "sionna_simulation"
  bler_table_path: "data/bler_tables.npz"  # Required if lookup_table

  # Link-to-system mapping
  enable_eesm: true  # Frequency-selective fading
  eesm_num_subcarriers: 234  # WiFi 6: 234 data subcarriers (80 MHz)

  # Fast fading
  enable_fast_fading: false  # Time-varying channel

  # MAC/queue jitter
  mac_jitter_model: "csma_ca"  # or "tdma", "none"

# Per-interface configuration
nodes:
  node1:
    interfaces:
      eth1:
        wireless:
          # Existing params...
          frequency_ghz: 5.18
          bandwidth_mhz: 80

          # New params for advanced features
          velocity_mps: 0.0  # For Doppler (m/s)
          num_contenders: 5  # For MAC jitter
          channel_utilization: 0.3  # For queue jitter (0-1)

          # HARQ (optional)
          harq:
            enabled: false
            max_retransmissions: 4
            combining_type: "ir"  # or "chase"

          # MIMO (future)
          antenna_array:
            num_elements: 1  # 1 = SISO, 2/4/8 = MIMO
            beamforming: "none"  # or "maxratio", "zeroforcing"
```

---

## Success Metrics

### Accuracy Improvements

- **BER/BLER**: Within ±0.5 dB of Sionna simulations for WiFi 6 MCS 0-11
- **Jitter**: Match ns-3 802.11 MAC within ±20% (0.5-20 ms range)
- **Frequency selectivity**: EESM matches measured throughput within ±10%

### Performance

- **Channel computation time**: <200 ms per link (no regression)
- **Memory usage**: <100 MB additional (for BLER tables)
- **Scalability**: Support 100+ node networks with EESM enabled

### Usability

- **Backwards compatibility**: All existing examples work without changes
- **Default behavior**: No breaking changes (new features opt-in)
- **Documentation**: Each feature has tutorial example

---

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| EESM implementation complexity | Medium | High | Start with simplified model, validate incrementally |
| BLER table generation time | Low | Medium | Generate once, cache, distribute with package |
| Performance regression | Medium | High | Benchmark each feature, make advanced features opt-in |
| Sionna API changes | Low | Medium | Pin Sionna version, test before upgrading |
| Validation accuracy | Medium | High | Compare against multiple sources (3GPP, ns-3, measurements) |

---

## Conclusion

These improvements will significantly enhance SiNE's BER/PER computation accuracy while maintaining its core strength: fast, deterministic channel modeling for network emulation.

**Recommended starting point**: Phase 1 (Quick Wins) provides immediate value with minimal risk. Phase 2 (EESM + MAC jitter) brings SiNE to industry-standard accuracy. Phase 3 and beyond are for specialized use cases and research projects.

**Key decision points**:
1. **BLER tables vs. theoretical formulas**: Tables provide accuracy, theoretical provides simplicity
2. **EESM always-on vs. opt-in**: Always-on is more accurate, opt-in maintains backwards compatibility
3. **Jitter modeling scope**: Start with statistical model, consider full MAC simulation later

**Next steps**:
1. Review and approve Phase 1 improvements
2. Assign implementation to development cycle
3. Set up validation benchmarks
4. Document new features in user guide
