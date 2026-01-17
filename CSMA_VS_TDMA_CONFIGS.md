# CSMA vs TDMA Configuration Examples

This document compares CSMA/CA (WiFi) and TDMA (military) MAC layer configurations in SiNE.

---

## CSMA/CA Configuration (WiFi 6 MANET)

**Use case**: WiFi 6 (802.11ax) MANETs with carrier sensing

**Key characteristics**:
- **Carrier sense range**: Nodes defer when medium is sensed busy (2.5× communication range)
- **Hidden node problem**: Nodes beyond CS range may collide
- **Traffic load**: Statistical duty cycle (e.g., 30%)
- **Spatial reuse**: Distant nodes transmit concurrently

### Configuration

```yaml
topology:
  enable_sinr: true

  nodes:
    node1:
      interfaces:
        eth1:
          wireless:
            # Physical layer
            position: {x: 0, y: 0, z: 1}
            frequency_ghz: 5.18
            bandwidth_mhz: 80
            rf_power_dbm: 20

            # Adaptive MCS (WiFi 6)
            mcs_table: examples/wifi6_adaptive/data/wifi6_mcs.csv
            mcs_hysteresis_db: 2.0

            # MAC layer: CSMA/CA model
            csma:
              enabled: true
              carrier_sense_range_multiplier: 2.5  # WiFi typical
              traffic_load: 0.3                     # 30% duty cycle

    node2:
      interfaces:
        eth1:
          wireless:
            position: {x: 100, y: 0, z: 1}
            frequency_ghz: 5.18
            bandwidth_mhz: 80
            rf_power_dbm: 20
            mcs_table: examples/wifi6_adaptive/data/wifi6_mcs.csv

            csma:
              enabled: true
              carrier_sense_range_multiplier: 2.5
              traffic_load: 0.3

    node3:
      interfaces:
        eth1:
          wireless:
            position: {x: 50, y: 86.6, z: 1}
            frequency_ghz: 5.18
            bandwidth_mhz: 80
            rf_power_dbm: 20
            mcs_table: examples/wifi6_adaptive/data/wifi6_mcs.csv

            csma:
              enabled: true
              carrier_sense_range_multiplier: 2.5
              traffic_load: 0.3

  links:
    - endpoints: [node1:eth1, node2:eth1]
    - endpoints: [node1:eth1, node3:eth1]
    - endpoints: [node2:eth1, node3:eth1]
```

### Expected Behavior

**Interference calculation**:
```
For link node1→node2:
  - Interferer: node3
  - Distance node3→node1: 100m
  - Communication range: ~150m (estimate at SNR threshold)
  - CS range: 150m × 2.5 = 375m

  Since 100m < 375m:
    Pr[node3 TX] = 0.0  (within CS range, defers due to carrier sensing)

  Expected interference: 0 dBm (no collision)
  SINR ≈ SNR (minimal interference)
```

**Throughput**: ~80-90% of rate (spatial reuse, limited collisions)

**Deployment output**:
```
Link: node1→node2 [wireless, CSMA model]
  SNR: 35.2 dB | SINR: 35.0 dB | Hidden nodes: 0/2 interferers
  Expected interference: -inf dBm (nodes within CS range)
  Delay: 0.33 ms | Jitter: 0.00 ms | Loss: 0.00% | Rate: 480 Mbps
```

---

## TDMA Configuration (Military MANET)

**Use case**: Military radios (WNW, MPU5, SINCGARS) with scheduled time slots

**Key characteristics**:
- **Slot assignment**: Pre-assigned, round-robin, random, or distributed
- **Deterministic interference**: Zero if orthogonal slots (FIXED/ROUND_ROBIN)
- **Throughput**: Fraction of frame allocated to node (e.g., 20% for 2/10 slots)
- **No carrier sensing**: Slots are scheduled, not sensed

### Configuration (Fixed Slots)

```yaml
topology:
  enable_sinr: true

  nodes:
    node1:
      interfaces:
        eth1:
          wireless:
            # Physical layer
            position: {x: 0, y: 0, z: 1}
            frequency_ghz: 5.18
            bandwidth_mhz: 20          # Military narrower BW
            rf_power_dbm: 30           # Higher power than WiFi

            # Fixed modulation (no adaptive MCS)
            modulation: qpsk
            fec_type: ldpc
            fec_code_rate: 0.5

            # MAC layer: TDMA model
            tdma:
              enabled: true
              slot_assignment_mode: fixed
              frame_duration_ms: 10.0
              num_slots: 10
              fixed_slot_map:
                node1: [0, 5]    # Owns slots 0 and 5 (20% of frame)
                node2: [1, 6]    # Owns slots 1 and 6 (20% of frame)
                node3: [2, 7]    # Owns slots 2 and 7 (20% of frame)

    node2:
      interfaces:
        eth1:
          wireless:
            position: {x: 100, y: 0, z: 1}
            frequency_ghz: 5.18
            bandwidth_mhz: 20
            rf_power_dbm: 30
            modulation: qpsk
            fec_type: ldpc
            fec_code_rate: 0.5

            tdma:
              enabled: true
              slot_assignment_mode: fixed
              # (same slot map as node1)

    node3:
      interfaces:
        eth1:
          wireless:
            position: {x: 50, y: 86.6, z: 1}
            frequency_ghz: 5.18
            bandwidth_mhz: 20
            rf_power_dbm: 30
            modulation: qpsk
            fec_type: ldpc
            fec_code_rate: 0.5

            tdma:
              enabled: true
              slot_assignment_mode: fixed
              # (same slot map as node1)

  links:
    - endpoints: [node1:eth1, node2:eth1]
    - endpoints: [node1:eth1, node3:eth1]
    - endpoints: [node2:eth1, node3:eth1]
```

### Expected Behavior

**Interference calculation**:
```
For link node1→node2:
  - Interferer: node3
  - node1 owns slots [0, 5]
  - node3 owns slots [2, 7]

  Slots overlap? No (orthogonal)
    Pr[node3 TX when node1 TX] = 0.0  (deterministic)

  Expected interference: 0 dBm (zero collision)
  SINR = SNR (no interference)
```

**Throughput**: 20% of rate (2 slots out of 10)

**Deployment output**:
```
Link: node1→node2 [wireless, TDMA fixed]
  SNR: 35.2 dB | SINR: 35.2 dB | Interferers: 0/2 deterministic (orthogonal slots)
  Expected interference: -inf dBm (zero collision probability)
  Delay: 0.33 ms | Jitter: 0.00 ms | Loss: 0.00% | Rate: 32 Mbps
  Throughput: 6.4 Mbps (20% slot ownership)
```

---

## Side-by-Side Comparison

| Feature | CSMA/CA (WiFi) | TDMA (Military) |
|---------|----------------|-----------------|
| **Access method** | Random backoff, carrier sensing | Scheduled time slots |
| **Interference** | Statistical (hidden node problem) | Deterministic (zero if orthogonal) |
| **Spatial reuse** | Yes (nodes beyond CS range) | No (time-domain separation) |
| **Throughput** | ~80-90% of rate (high spatial reuse) | Slot ownership fraction (e.g., 20%) |
| **Configuration complexity** | Simple (2 params) | Medium (slot map or mode) |
| **Typical radios** | WiFi 6 (802.11ax) | WNW, MPU5, SINCGARS |
| **SINR vs SNR** | SINR < SNR (statistical interference) | SINR = SNR (orthogonal slots) |
| **Use case** | Commercial WiFi MANETs | Military tactical networks |

---

## Configuration Parameters

### CSMA/CA Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `enabled` | bool | false | Enable CSMA/CA model |
| `carrier_sense_range_multiplier` | float | 2.5 | CS range / communication range |
| `traffic_load` | float | 0.3 | Traffic duty cycle (30%) |

**Typical values**:
- WiFi: `carrier_sense_range_multiplier: 2.5`, `traffic_load: 0.3`
- High traffic: `traffic_load: 0.5-0.7`
- Low traffic: `traffic_load: 0.1-0.2`

---

### TDMA Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `enabled` | bool | false | Enable TDMA model |
| `frame_duration_ms` | float | 10.0 | TDMA frame duration (ms) |
| `num_slots` | int | 10 | Number of slots per frame |
| `slot_assignment_mode` | enum | round_robin | fixed, round_robin, random, distributed |
| `fixed_slot_map` | dict | null | Node→slot mapping (FIXED mode only) |
| `slot_probability` | float | 0.1 | Slot ownership probability (RANDOM/DISTRIBUTED) |

**Typical values**:
- Military TDMA: `frame_duration_ms: 10.0`, `num_slots: 10-20`
- Fixed allocation: `slot_assignment_mode: fixed`, specify `fixed_slot_map`
- Round-robin: `slot_assignment_mode: round_robin` (automatic allocation)

---

## Mixed Scenarios

### Scenario 1: WiFi Nodes + Military Nodes (Different Frequencies)

```yaml
nodes:
  wifi_node1:
    interfaces:
      eth1:
        wireless:
          frequency_ghz: 5.18  # WiFi
          csma:
            enabled: true

  military_node1:
    interfaces:
      eth1:
        wireless:
          frequency_ghz: 1.76  # Military L-band
          tdma:
            enabled: true
            slot_assignment_mode: fixed
```

**Note**: Different frequencies → separate interference domains (use ACLR in Phase 2)

---

### Scenario 2: Same Frequency, Different MAC (NOT RECOMMENDED)

```yaml
nodes:
  wifi_node1:
    interfaces:
      eth1:
        wireless:
          frequency_ghz: 5.18
          csma:
            enabled: true

  military_node1:
    interfaces:
      eth1:
        wireless:
          frequency_ghz: 5.18  # Same freq as WiFi
          tdma:
            enabled: true
```

**Warning**: Mixing MAC models on same frequency is not realistic. Choose one MAC model per frequency group.

---

## Choosing the Right MAC Model

| Scenario | Recommended MAC Model |
|----------|----------------------|
| WiFi 6 MANET (802.11ax) | CSMA/CA |
| Military tactical network (WNW, MPU5) | TDMA (fixed or round-robin) |
| Commercial mesh network (802.11s) | CSMA/CA |
| Satellite uplink (DAMA) | TDMA (distributed) |
| LoRa MANET | CSMA/CA (adapted params) |
| SINCGARS (freq hopping) | TDMA (fixed) + freq hopping (future) |
| Testing worst-case interference | Neither (use Phase 1 all-TX baseline) |

---

## Validation Examples

### CSMA Validation

```bash
# Deploy CSMA topology
sudo $(which uv) run sine deploy examples/sinr_csma_example.yaml

# Check SINR (should be close to SNR if all nodes within CS range)
# Expected: SINR ≈ SNR - 0-3 dB

# Measure throughput
docker exec clab-sinr-csma-wifi6-node1 iperf3 -c 192.168.100.2 -t 10

# Expected: ~400-450 Mbps (80-90% of 500 Mbps theoretical)
```

### TDMA Validation

```bash
# Deploy TDMA topology
sudo $(which uv) run sine deploy examples/sinr_tdma_fixed/network.yaml

# Check SINR (should equal SNR with orthogonal slots)
# Expected: SINR = SNR (zero interference)

# Measure throughput
docker exec clab-sinr-tdma-node1 iperf3 -c 192.168.100.2 -t 10

# Expected: ~6-7 Mbps (20% of 32 Mbps theoretical, 2/10 slots)
```

---

## Summary

- **CSMA/CA**: Use for WiFi MANETs, commercial mesh networks
  - Higher throughput (spatial reuse)
  - Statistical interference (hidden node problem)
  - Simple configuration (2 params)

- **TDMA**: Use for military MANETs, satellite networks
  - Deterministic interference (zero if orthogonal)
  - Lower throughput (slot ownership fraction)
  - More complex configuration (slot assignment)

Both models are **lightweight statistical abstractions** (not discrete-event simulation), appropriate for network emulation.
