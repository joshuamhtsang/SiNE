# WiFi 6 Adaptive MCS - Automatic Modulation Selection

## Overview

This example demonstrates **adaptive MCS (Modulation and Coding Scheme) selection** similar to WiFi 6 (802.11ax). The system automatically selects the optimal modulation and coding based on current SNR conditions, with hysteresis to prevent rapid switching.

## Scenario Details

- **Technology**: WiFi 6 (802.11ax) emulation
- **Frequency**: 5.18 GHz (Channel 36)
- **Bandwidth**: 80 MHz
- **Distance**: 20m (Access Point to Client)
- **MCS Range**: MCS 0 (BPSK) to MCS 11 (1024-QAM)
- **Hysteresis**: 2 dB (prevents rapid MCS changes)

## Adaptive MCS Features

### MCS Table (`data/wifi6_mcs.csv`)

The MCS table defines available modulation/coding options:

| MCS | Modulation | Code Rate | Min SNR | Data Rate (80 MHz) |
|-----|------------|-----------|---------|-------------------|
| 0   | BPSK       | 1/2       | 5 dB    | 32 Mbps           |
| 1   | QPSK       | 1/2       | 8 dB    | 64 Mbps           |
| 2   | QPSK       | 3/4       | 11 dB   | 96 Mbps           |
| 3   | 16-QAM     | 1/2       | 14 dB   | 128 Mbps          |
| 4   | 16-QAM     | 3/4       | 17 dB   | 192 Mbps          |
| 5   | 64-QAM     | 2/3       | 20 dB   | 213 Mbps          |
| 6   | 64-QAM     | 3/4       | 23 dB   | 240 Mbps          |
| 7   | 64-QAM     | 5/6       | 26 dB   | 267 Mbps          |
| 8   | 256-QAM    | 3/4       | 29 dB   | 320 Mbps          |
| 9   | 256-QAM    | 5/6       | 32 dB   | 356 Mbps          |
| 10  | 1024-QAM   | 3/4       | 35 dB   | 400 Mbps          |
| 11  | 1024-QAM   | 5/6       | 38 dB   | 533 Mbps          |

### Hysteresis Mechanism

Hysteresis prevents rapid MCS switching when SNR fluctuates near thresholds:

- **Upgrade**: SNR must exceed `min_snr_db + hysteresis_db` (e.g., 25 dB to upgrade from MCS 6→7 if threshold is 23 dB + 2 dB hysteresis)
- **Downgrade**: Immediate when SNR drops below current MCS threshold
- **Default hysteresis**: 2 dB

## Expected Results

At 20m in free-space with 20 dBm TX power:

- **SNR**: ~42 dB (excellent)
- **Selected MCS**: MCS 11 (1024-QAM, rate-5/6)
- **Data Rate**: ~533 Mbps

## Deployment

```bash
# 1. Start channel server
uv run sine channel-server

# 2. Deploy (requires sudo for netem)
sudo $(which uv) run sine deploy examples/wifi6_adaptive/network.yaml

# The deployment output will show the selected MCS:
# Link Parameters:
#   node1:eth1 ↔ node2:eth1 [wireless]
#     MCS: 11 (1024qam, rate-0.833, ldpc)
#     Delay: 0.07 ms | Jitter: 0.00 ms | Loss: 0.00% | Rate: 532.5 Mbps
# IP addresses are automatically configured from the topology YAML

# 3. Test throughput with iperf3
# Terminal 1 (server):
docker exec -it clab-wifi6-adaptive-node1 iperf3 -s

# Terminal 2 (client):
docker exec -it clab-wifi6-adaptive-node2 iperf3 -c 192.168.1.1

# 4. Cleanup
sudo $(which uv) run sine destroy examples/wifi6_adaptive/network.yaml
```

## Use Cases

### 1. **WiFi Performance Testing**
Test application behavior with realistic WiFi 6 data rates and MCS transitions.

### 2. **Range Testing**
Increase distance to see MCS downgrade as SNR decreases:
- 0-10m: MCS 10-11 (1024-QAM, 400-533 Mbps)
- 10-30m: MCS 7-9 (64/256-QAM, 267-356 Mbps)
- 30-50m: MCS 4-6 (16/64-QAM, 192-240 Mbps)
- 50m+: MCS 0-3 (BPSK/QPSK, 32-96 Mbps)

### 3. **Mobility Scenarios**
Enable mobility mode to see dynamic MCS selection as devices move:
```bash
sudo $(which uv) run sine deploy --enable-mobility examples/wifi6_adaptive/network.yaml
```

### 4. **Rate Adaptation Algorithm Testing**
Validate transport protocol behavior (TCP congestion control, video ABR) with realistic rate changes.

## Configuration

### Custom MCS Tables

Create your own MCS table CSV with required columns:

```csv
mcs_index,modulation,code_rate,min_snr_db,fec_type,bandwidth_mhz
0,bpsk,0.5,5.0,ldpc,80
1,qpsk,0.5,8.0,ldpc,80
...
```

**Required fields:**
- `mcs_index`: Unique integer index
- `modulation`: bpsk, qpsk, 16qam, 64qam, 256qam, 1024qam
- `code_rate`: FEC code rate (0-1)
- `min_snr_db`: Minimum SNR threshold

**Optional fields:**
- `fec_type`: ldpc (default), polar, turbo, none
- `bandwidth_mhz`: For documentation/reference

### Adjusting Hysteresis

```yaml
wireless:
  mcs_table: path/to/custom_mcs.csv
  mcs_hysteresis_db: 3.0  # Increase for more stable MCS, decrease for faster adaptation
```

## Comparison: Adaptive vs Fixed MCS

| Feature | Adaptive MCS | Fixed MCS |
|---------|--------------|-----------|
| **Configuration** | `mcs_table` path | `modulation`, `fec_type`, `fec_code_rate` |
| **Link adaptation** | Yes, based on SNR | No, static |
| **Mobility support** | Yes, MCS changes with distance | No |
| **Realism** | High (like real WiFi) | Medium (test-only) |
| **Use case** | Production testing, validation | Baseline, controlled tests |

## Notes

- The MCS index is tracked per-link for bidirectional links
- Deployment summary shows selected MCS for each link direction
- Use `--enable-mobility` to see dynamic MCS transitions as position changes
- The hysteresis prevents "ping-pong" MCS switching at threshold boundaries
