# Vacuum 20m - Free-Space Baseline Example

## Overview

This example demonstrates free-space wireless propagation with two nodes separated by 20 meters in vacuum (no obstacles or reflections). It serves as a baseline for comparing against more complex scenarios.

## Scenario Details

- **Distance**: 20m separation along X-axis
- **Propagation**: Free-space (vacuum scene, no reflections)
- **Frequency**: 5.18 GHz (WiFi 6, Channel 36)
- **Bandwidth**: 80 MHz
- **Modulation**: 64-QAM with LDPC FEC (rate 1/2)
- **TX Power**: 20 dBm
- **Antenna**: Isotropic pattern, 0 dBi gain

## Expected Results

Based on free-space path loss calculations:

- **Free-Space Path Loss (FSPL)**: ~68.3 dB
- **Received Power**: ~-48.3 dBm
- **Noise Floor**: ~-88 dBm (80 MHz BW, 7 dB NF)
- **SNR**: ~39.7 dB (excellent)
- **Link Quality**: Near-zero BER/BLER
- **Path Type**: Single line-of-sight (LOS) path

## Deployment

```bash
# 1. Start channel server
uv run sine channel-server

# 2. Deploy (in another terminal, requires sudo for netem)
# IP addresses are automatically configured from the topology YAML
sudo $(which uv) run sine deploy examples/vacuum_20m/network.yaml

# 3. Test connectivity with iperf3
# Terminal 1 (node1 server):
docker exec -it clab-vacuum-20m-node1 iperf3 -s

# Terminal 2 (node2 client):
docker exec -it clab-vacuum-20m-node2 iperf3 -c 192.168.1.1

# 4. Cleanup
sudo $(which uv) run sine destroy examples/vacuum_20m/network.yaml
```

## Use Cases

- **Baseline Testing**: Establish maximum link performance without obstacles
- **Validation**: Verify free-space path loss calculations match theory
- **Comparison**: Benchmark against scenarios with multipath, obstacles
- **Range Testing**: Compare theoretical vs. emulated maximum range

## Key Learnings

This example demonstrates:
- How SiNE computes free-space path loss using ray tracing
- The relationship between distance and received signal strength
- Baseline netem parameters (delay from propagation, minimal loss)
- Single-path propagation (no multipath fading)
