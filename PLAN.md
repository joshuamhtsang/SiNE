# Future Enhancements

## Spread Spectrum Support

### Overview

Spread spectrum techniques trade bandwidth for SNR tolerance, enabling communication at low and even negative SNR values. This section outlines how to extend SiNE to support these systems.

### Spread Spectrum Techniques

#### 1. Direct Sequence Spread Spectrum (DSSS)
- Multiplies data by a high-rate pseudo-noise (PN) code (e.g., 11 chips/bit in 802.11b)
- **Processing gain** = 10·log₁₀(chip_rate / data_rate)
- Example: 11 Mcps / 1 Mbps = 10.4 dB processing gain
- Can operate at SNR as low as **-10 to -15 dB** (after despreading)

#### 2. Frequency Hopping Spread Spectrum (FHSS)
- Rapidly hops carrier frequency across wide band
- Provides interference avoidance rather than true processing gain
- Used in Bluetooth, some military systems

#### 3. Chirp Spread Spectrum (CSS)
- Used in **LoRa** - sweeps frequency linearly across bandwidth
- Processing gain = 2^SF (spreading factor 7-12)
- LoRa SF12 can operate at **-20 dB SNR**
- Very low data rates (few hundred bps to ~50 kbps)

#### 4. Code Division Multiple Access (CDMA)
- DSSS with orthogonal codes for multiple users
- GPS operates at approximately **-30 dB SNR** (massive processing gain from 1.023 Mcps code)

### Current SiNE Capabilities

| Aspect | Current SiNE | Spread Spectrum Needs |
|--------|--------------|----------------------|
| **Processing gain** | Not modeled | Need to add Gp to effective SNR |
| **BER formulas** | Standard BPSK/QAM | Need DSSS/CSS-specific formulas |
| **Chip-level simulation** | No | Sionna can do this, but computationally expensive |
| **Rake receiver** | No | Combines multipath (DSSS benefit) |
| **Despreading** | No | Converts spread signal back |

### Recommended Implementation: Processing Gain Model

The simplest approach is to model processing gain as an SNR offset, without chip-level simulation.

#### Extended CSV Format

Add `spreading_factor` and `processing_gain_db` columns to MCS table:

```csv
mcs_index,modulation,code_rate,min_snr_db,fec_type,spreading_factor,processing_gain_db
0,bpsk,0.5,-20.0,none,4096,36.1
1,bpsk,0.5,-17.5,none,2048,33.1
2,bpsk,0.5,-15.0,none,1024,30.1
3,bpsk,0.5,-12.5,none,512,27.1
4,bpsk,0.5,-10.0,none,256,24.1
5,bpsk,0.5,-7.5,none,128,21.1
6,bpsk,0.5,-5.0,none,64,18.1
```

Example LoRa-like table (`data/lora_mcs.csv`):

```csv
mcs_index,modulation,code_rate,min_snr_db,fec_type,spreading_factor,processing_gain_db
0,css,0.8,-20.0,hamming,4096,36.1
1,css,0.8,-17.5,hamming,2048,33.1
2,css,0.8,-15.0,hamming,1024,30.1
3,css,0.8,-12.5,hamming,512,27.1
4,css,0.8,-10.0,hamming,256,24.1
5,css,0.8,-7.5,hamming,128,21.1
```

#### Channel Computation Changes

In `compute_channel_for_link()`:

```python
# After SNR calculation
if mcs.processing_gain_db:
    effective_snr = snr_db + mcs.processing_gain_db
else:
    effective_snr = snr_db

# Use effective_snr for BER calculation
ber = ber_calc.theoretical_ber_awgn(effective_snr)
```

#### Rate Calculation Changes

For spread spectrum, data rate is reduced by spreading factor:

```python
if mcs.spreading_factor and mcs.spreading_factor > 1:
    # Spread spectrum: rate reduced by spreading
    raw_rate = bandwidth_hz / spreading_factor * bits_per_symbol
else:
    # Standard modulation
    raw_rate = bandwidth_hz * bits_per_symbol * ofdm_efficiency

rate_mbps = raw_rate * code_rate * (1 - per) / 1e6
```

#### Schema Changes

Add to `MCSEntry`:
- `spreading_factor: int | None = None` (default 1 = no spreading)
- `processing_gain_db: float | None = None` (default 0)

#### Example YAML (LoRa-like)

```yaml
interfaces:
  eth1:
    wireless:
      position: {x: 0, y: 0, z: 1}
      frequency_ghz: 0.868          # EU LoRa band
      bandwidth_mhz: 0.125          # 125 kHz
      rf_power_dbm: 14.0
      mcs_table: data/lora_mcs.csv
      mcs_hysteresis_db: 3.0
```

### Implementation Order

1. Extend `MCSEntry` with `spreading_factor` and `processing_gain_db` fields
2. Update CSV parsing to handle optional spread spectrum columns
3. Modify `compute_channel_for_link()` to apply processing gain to effective SNR
4. Update rate calculation to account for spreading factor
5. Create `data/lora_mcs.csv` and `data/dsss_mcs.csv` example tables
6. Create `examples/lora_longrange/` example topology

### Limitations of This Approach

- **No chip-level simulation**: Doesn't model actual spreading/despreading
- **No Rake receiver**: Doesn't combine multipath constructively (DSSS benefit in multipath channels)
- **Simplified BER**: Uses BPSK formula with processing gain offset, not true spread spectrum BER curves
- **No interference modeling**: Processing gain against narrowband interference not modeled

For most network emulation use cases (testing routing protocols, application behavior over lossy links), this simplified model is sufficient. True chip-level simulation would require Sionna's link-level modules with custom spreading code implementation.
