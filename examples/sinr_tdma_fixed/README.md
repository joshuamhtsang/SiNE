# TDMA Fixed Slots Example

This example demonstrates SiNE's TDMA statistical model with pre-assigned orthogonal slots, implementing Phase 1.6 of the SINR plan.

## Overview

**Topology**: 3-node equilateral triangle, 100m sides
**Frequency**: 5.18 GHz (same PHY as WiFi for comparison)
**Bandwidth**: 80 MHz
**Modulation**: Fixed 64-QAM, LDPC rate-2/3
**MAC**: TDMA with fixed slot assignment

## TDMA Fixed Slots Model

The fixed TDMA model uses pre-assigned slots for deterministic channel access:

- **Frame duration**: 10ms (military typical)
- **Number of slots**: 10 per frame
- **Slot assignment**: Each node owns specific slots
- **Interference**: Zero (orthogonal time slots)

### Slot Assignments

```
Frame: [0][1][2][3][4][5][6][7][8][9] (10ms total, 1ms per slot)
Node1:  ✓  -  -  -  -  ✓  -  -  -  -   (2 slots, 20%)
Node2:  -  ✓  -  -  -  -  ✓  -  -  -   (2 slots, 20%)
Node3:  -  -  ✓  -  -  -  -  ✓  -  -   (2 slots, 20%)
```

### Configuration

```yaml
wireless:
  tdma:
    enabled: true
    frame_duration_ms: 10.0
    num_slots: 10
    slot_assignment_mode: fixed
    fixed_slot_map:
      node1: [0, 5]    # 20% ownership
      node2: [1, 6]    # 20% ownership
      node3: [2, 7]    # 20% ownership
```

## Deployment

```bash
# Start channel server
uv run sine channel-server

# Deploy
sudo $(which uv) run sine deploy examples/sinr_tdma_fixed/network.yaml

# Check status
uv run sine status
```

## Expected Results

### Link Quality

```
Link: node1→node2 [wireless, TDMA fixed]
  SNR: 35.2 dB | SINR: 35.2 dB | Interferers: 0/2 deterministic (orthogonal slots)
  Expected interference: -inf dBm (zero collision probability)
  Delay: 0.33 ms | Jitter: 0.00 ms | Loss: 0.00% | Rate: 96 Mbps
  Throughput: 19.2 Mbps (20% slot ownership)
```

**Key observations**:
- SINR = SNR (no interference from orthogonal slots)
- Rate: 96 Mbps = 480 Mbps × 0.2 (20% slot ownership)
- Zero packet loss (no collisions)

### CSMA vs TDMA Comparison

| Metric | CSMA (WiFi) | TDMA (Military) | Winner |
|--------|-------------|-----------------|--------|
| **Throughput** | ~400-450 Mbps | ~90-96 Mbps | CSMA (4-5×) |
| **Collisions** | Statistical (hidden nodes) | Zero (orthogonal) | TDMA |
| **Latency variance** | High (random backoff) | Low (predictable slots) | TDMA |
| **QoS guarantee** | Best-effort | Guaranteed slots | TDMA |
| **Fairness** | Proximity-based | Equal slots | TDMA |
| **Anti-jam** | Jammer causes DoS | Can use unjammed slots | TDMA |

**Military priority**: Deterministic 20 Mbps > Statistical 400 Mbps

### Throughput Validation

```bash
# Configure IPs
docker exec clab-sinr-tdma-fixed-node1 ip addr add 192.168.100.1/24 dev eth1
docker exec clab-sinr-tdma-fixed-node2 ip addr add 192.168.100.2/24 dev eth1

# Start server
docker exec clab-sinr-tdma-fixed-node1 iperf3 -s &

# Run client (30 sec test)
docker exec clab-sinr-tdma-fixed-node2 iperf3 -c 192.168.100.1 -t 30

# Expected: ~90-95 Mbps (95-99% of 96 Mbps theoretical)
# Protocol overhead accounts for 1-5% loss
```

## Why Military Radios Accept Lower Throughput

TDMA provides **determinism and reliability** over raw speed:

### Combat Scenario Example

**Voice/command traffic**: Needs reliable 20 Mbps, not statistical 400 Mbps

| Requirement | CSMA Result | TDMA Result |
|-------------|-------------|-------------|
| "When will my packet arrive?" | "Maybe 10-100ms" | "In slot 5 (±1ms)" |
| "Will it collide?" | "9% chance" | "0% (guaranteed)" |
| "Jammer impact?" | "All defer (DoS)" | "Can use unjammed slots" |

**TDMA wins**: "Zero collisions guaranteed" > "9% statistical collision rate"

## Throughput Calculation

```
PHY rate: 480 Mbps (80 MHz, 64-QAM, LDPC rate-2/3, ~0.8 efficiency)
Slot ownership: 2/10 = 20%
Effective rate: 480 × 0.2 = 96 Mbps

Applied to netem:
  rate_mbps = 96  # Limits TCP/UDP throughput to 96 Mbps
```

## Cleanup

```bash
sudo $(which uv) run sine destroy examples/sinr_tdma_fixed/network.yaml
```

## See Also

- [sinr_tdma_roundrobin](../sinr_tdma_roundrobin/) - Automatic cyclic slot assignment (33.3% per node)
- [sinr_csma_example](../sinr_csma_example/) - WiFi CSMA/CA comparison
- [PLAN_SINR.md](../../PLAN_SINR.md) - Phase 1.6 specification
- [tdma_model.py](../../src/sine/channel/tdma_model.py) - Implementation
