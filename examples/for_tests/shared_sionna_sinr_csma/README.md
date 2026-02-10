# CSMA/CA Statistical Model Example

This example demonstrates SiNE's CSMA/CA statistical model for WiFi 6 MANETs, implementing Phase 1.5 of the SINR plan.

## Overview

**Topology**: 3-node equilateral triangle, 100m sides
**Frequency**: 5.18 GHz (WiFi 6 channel 36)
**Bandwidth**: 80 MHz
**Modulation**: Adaptive MCS (WiFi 6 table) or fixed 64-QAM

## CSMA/CA Model

The statistical CSMA/CA model captures WiFi carrier sensing behavior without full MAC simulation:

- **Carrier sense range**: 2.5× communication range (WiFi typical)
- **Traffic load**: 30% duty cycle (default)
- **Spatial reuse**: Nodes beyond CS range transmit concurrently
- **Hidden node problem**: Nodes beyond CS range may collide

### How It Works

For each link TX→RX, the model computes per-interferer transmission probability:

```
Pr[interferer_i TX] = {
  0.0   if dist(interferer, TX) < CS_range  (defers due to carrier sensing)
  0.3   if dist(interferer, TX) ≥ CS_range  (hidden node, traffic_load)
}

Expected interference = Σ Pr[TX_i] × I_i (linear power)
SINR = signal_power / (noise_power + expected_interference)
```

### Configuration

```yaml
wireless:
  csma:
    enabled: true                          # Enable CSMA/CA model
    carrier_sense_range_multiplier: 2.5    # CS range / communication range
    traffic_load: 0.3                      # Traffic duty cycle (30%)
```

## Deployment

```bash
# Start channel server
uv run sine channel-server

# Deploy (in another terminal)
sudo $(which uv) run sine deploy examples/sinr_csma_example.yaml

# Check deployment
uv run sine status
```

## Expected Results

### Link Quality

```
Link: node1→node2 [wireless, CSMA model]
  SNR: 35.2 dB | SINR: 32.1 dB | Hidden nodes: 0/2 interferers
  Expected interference: -5.2 dBm (vs -2.3 dBm all-TX)
  Delay: 0.33 ms | Jitter: 0.00 ms | Loss: 0.01% | Rate: 480 Mbps
```

### CSMA vs All-TX Comparison

| Metric | All-TX (worst-case) | CSMA (realistic) | Improvement |
|--------|---------------------|------------------|-------------|
| **SINR** | 28.4 dB | 32.1 dB | +3.7 dB |
| **Expected interference** | -2.3 dBm | -5.2 dBm | -2.9 dB (lower) |
| **Hidden nodes** | N/A (all transmit) | 0/2 | Spatial reuse |

**Note**: In this topology, all nodes are within carrier sense range (100m < 375m CS range), so no hidden nodes exist. All interferers defer due to carrier sensing.

### Throughput Test

```bash
# Configure IP addresses
docker exec clab-sh-sio-sinr-csma-node1 ip addr add 192.168.100.1/24 dev eth1
docker exec clab-sh-sio-sinr-csma-node2 ip addr add 192.168.100.2/24 dev eth1

# Start iperf3 server
docker exec clab-sh-sio-sinr-csma-node1 iperf3 -s &

# Run iperf3 client
docker exec clab-sh-sio-sinr-csma-node2 iperf3 -c 192.168.100.1 -t 30

# Expected: ~400-450 Mbps (80-90% of 480 Mbps theoretical)
# Reason: High spatial reuse, nodes defer when others transmit
```

## Hidden Node Scenario

To test hidden node behavior, modify node3 position:

```yaml
node3:
  interfaces:
    eth1:
      wireless:
        position: {x: 500, y: 0, z: 1}  # 500m from node1 (beyond CS range)
```

Expected:
- Node3 is hidden from node1 (500m > 375m CS range)
- Pr[node3 TX] = 0.3 (traffic_load)
- Higher interference on node1→node2 link
- SINR degradation vs co-located scenario

## Cleanup

```bash
sudo $(which uv) run sine destroy examples/sinr_csma_example.yaml
```

## References

- [PLAN_SINR.md](../../PLAN_SINR.md) - Phase 1.5 specification
- [csma_model.py](../../src/sine/channel/csma_model.py) - Implementation
- [test_csma_model.py](../../tests/test_csma_model.py) - Unit tests
