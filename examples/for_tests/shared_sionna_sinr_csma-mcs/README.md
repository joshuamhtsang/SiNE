# CSMA + Adaptive MCS Integration Test - Hidden Node Scenario

This example validates that **MCS selection uses SINR (not SNR)** when a CSMA MAC model is present, ensuring interference is properly accounted for in modulation selection. It demonstrates the **hidden node problem** with asymmetric connectivity.

## Topology

Linear arrangement with hidden node:

```
node1 ──────────────── node2 ────── node3
(0,0,1)              (30,0,1)   (40,0,1)
```

**Distances:**
- node1 ↔ node2: **30m** (node1 is HIDDEN from node2)
- node2 ↔ node3: **10m** (primary test link)
- node1 ↔ node3: **40m**

**CSMA Carrier Sense:**
- Communication range: 11m (determined by `communication_range_snr_threshold_db: 40.4`)
- CS range: 11m × 2.5 = **27.5m**
- **node1 @ 30m is OUTSIDE carrier sense range** → hidden node!

## Hidden Node Problem

Node1 is **hidden** from node2/node3 because it's outside the carrier sense range (30m > 27.5m):

- **node1 CANNOT sense** node2/node3 transmissions
- **node2/node3 CANNOT sense** node1 transmissions
- **Collisions occur** when node1 transmits while node2/node3 are transmitting
- **Result**: node1's transmissions have **NEGATIVE SINR** (interference > signal)

### Asymmetric Connectivity

| Link | SINR | Loss | Rate | Can Communicate? |
|------|------|------|------|------------------|
| **node1 → node2** | **-4.3 dB** ❌ | 100% | 0.1 Mbps | **NO** (negative SINR) |
| **node1 → node3** | **-6.8 dB** ❌ | 100% | 0.1 Mbps | **NO** (negative SINR) |
| **node2 → node1** | **31.7 dB** ✅ | 0% | 384 Mbps | **YES** (high SINR) |
| **node3 → node1** | **29.2 dB** ✅ | 0% | 384 Mbps | **YES** (high SINR) |
| **node2 → node3** | **17.3 dB** ✅ | 0% | 192 Mbps | **YES** (medium SINR) |
| **node3 → node2** | **14.8 dB** ✅ | 0.04% | 128 Mbps | **YES** (medium SINR) |

**Key insight**: Node1 can **RECEIVE** traffic (forward path works) but **CANNOT SEND** traffic (return path fails).

## Deployment Parameters

When deployed, the system computes these parameters:

### Node1 (Hidden Node) - CANNOT Transmit

```
Per-Destination Parameters for node1:
┌──────────────┬──────────┬──────────┬─────────┬──────────┐
│ Destination  │    Delay │   Jitter │  Loss % │     Rate │
├──────────────┼──────────┼──────────┼─────────┼──────────┤
│ node2 (None) │ 0.000 ms │ 0.000 ms │ 100.00% │ 0.1 Mbps │  ← SINR = -4.3 dB
│ node3 (None) │ 0.000 ms │ 0.000 ms │ 100.00% │ 0.1 Mbps │  ← SINR = -6.8 dB
└──────────────┴──────────┴──────────┴─────────┴──────────┘
```

**Explanation**: Negative SINR (interference from node2/node3 overwhelms node1's signal at receivers) → 100% packet loss → minimal rate (0.1 Mbps fallback).

### Node2 - Asymmetric Rates

```
Per-Destination Parameters for node2:
┌──────────────┬──────────┬──────────┬────────┬────────────┐
│ Destination  │    Delay │   Jitter │ Loss % │       Rate │
├──────────────┼──────────┼──────────┼────────┼────────────┤
│ node1 (None) │ 0.000 ms │ 0.000 ms │  0.00% │ 384.0 Mbps │  ← SINR = 31.7 dB (high MCS)
│ node3 (None) │ 0.000 ms │ 0.000 ms │  0.00% │ 192.0 Mbps │  ← SINR = 17.3 dB (medium MCS)
└──────────────┴──────────┴──────────┴────────┴────────────┘
```

**Explanation**:
- **node2→node1**: High SINR (31.7 dB, minimal interference) → MCS 5-6 (64-QAM) → 384 Mbps
- **node2→node3**: Medium SINR (17.3 dB, interference from node1 @ 40m) → MCS 4 (16-QAM, rate-0.75) → 192 Mbps

### Node3 - Even More Asymmetry

```
Per-Destination Parameters for node3:
┌──────────────┬──────────┬──────────┬────────┬────────────┐
│ Destination  │    Delay │   Jitter │ Loss % │       Rate │
├──────────────┼──────────┼──────────┼────────┼────────────┤
│ node1 (None) │ 0.000 ms │ 0.000 ms │  0.00% │ 384.0 Mbps │  ← SINR = 29.2 dB (high MCS)
│ node2 (None) │ 0.000 ms │ 0.000 ms │  0.04% │ 128.0 Mbps │  ← SINR = 14.8 dB (lower MCS)
└──────────────┴──────────┴──────────┴────────┴────────────┘
```

**Explanation**:
- **node3→node1**: High SINR (29.2 dB, minimal interference) → MCS 5-6 (64-QAM) → 384 Mbps
- **node3→node2**: Lower SINR (14.8 dB, interference from node1 @ 30m, **closer than for node2→node3**) → MCS 3 (16-QAM, rate-0.5) → 128 Mbps

## SNR vs SINR: Why Asymmetric?

### SNR is Symmetric ✅

For the node2 ↔ node3 link (10m apart):

| Direction | SNR | Why Same? |
|-----------|-----|-----------|
| node2 → node3 | **41.2 dB** | Same distance (10m), same TX power (20 dBm), same antenna (iso, 0 dBi) |
| node3 → node2 | **41.2 dB** | Same distance (10m), same TX power (20 dBm), same antenna (iso, 0 dBi) |

**Conclusion**: SNR is symmetric because path loss is symmetric (same distance).

### SINR is Asymmetric ❌

The **interferer (node1)** is at different distances from each receiver:

| Link | SINR | Interferer Distance | Interference Power | Explanation |
|------|------|--------------------|--------------------|-------------|
| node2 → node3 | **17.3 dB** | node1 @ **40m** from node3 | -64.0 dBm | Farther interferer = weaker interference = higher SINR |
| node3 → node2 | **14.8 dB** | node1 @ **30m** from node2 | -61.5 dBm | Closer interferer = stronger interference = lower SINR |

**Path loss difference**: 40m vs 30m = ~2.5 dB more path loss at 40m → SINR difference of 2.5 dB ✅

**Conclusion**: SINR asymmetry is **correct behavior** due to geometry. Closer interferer = lower SINR.

## MCS Selection Based on SINR

The rate limits reflect MCS selection based on **SINR** (not SNR):

| Link | SNR | SINR | Selected MCS | Rate | Calculation |
|------|-----|------|--------------|------|-------------|
| node2→node1 | ~31 dB | **31.7 dB** | MCS 5-6 (64-QAM) | 384 Mbps | 80 MHz × 6 bits × 0.8 code_rate × 0.8 eff = 307 Mbps (with overhead) |
| node2→node3 | ~41 dB | **17.3 dB** | MCS 4 (16-QAM, rate-0.75) | 192 Mbps | 80 MHz × 4 bits × 0.75 × 0.8 = 192 Mbps ✅ |
| node3→node1 | ~29 dB | **29.2 dB** | MCS 5-6 (64-QAM) | 384 Mbps | Same as node2→node1 |
| node3→node2 | ~41 dB | **14.8 dB** | MCS 3 (16-QAM, rate-0.5) | 128 Mbps | 80 MHz × 4 bits × 0.5 × 0.8 = 128 Mbps ✅ |

**Critical**: If MCS were selected on SNR alone, node2→node3 would use MCS 6+ (256+ Mbps) and suffer massive packet loss due to interference.

## Integration Tests

The test suite in [test_csma_mcs_comprehensive.py](../../../tests/integration/shared_bridge/sionna_engine/sinr/test_csma_mcs_comprehensive.py) validates:

### 1. ✅ MCS Index Validation (`test_csma_mcs_index_validation`)

**New enhancement**: Queries the mobility API to extract actual MCS index values.

**Validates**:
- ✓ SNR is symmetric (41.2 dB both directions)
- ✓ SINR is asymmetric (17.3 dB vs 14.8 dB due to interferer distance)
- ✓ MCS selected based on SINR (MCS 3-5 for SINR ~15-17 dB, not MCS 6+ for SNR ~41 dB)
- ✓ MCS index matches SINR threshold from WiFi 6 MCS table

**Example output**:
```
MCS Index Validation Results:
======================================================================
Link node2 → node3:
  SNR: 41.2 dB | SINR: 17.3 dB | MCS: 4
  Interferer (node1) at 40m from RX

Link node3 → node2:
  SNR: 41.2 dB | SINR: 14.8 dB | MCS: 3
  Interferer (node1) at 30m from RX

✓ SNR symmetric: 41.2 dB ≈ 41.2 dB (same distance)
✓ SINR asymmetric: 17.3 dB > 14.8 dB (closer interferer = lower SINR)
✓ MCS selected based on SINR (not SNR)
======================================================================
```

### 2. ✅ TCP Failure Test (`test_csma_mcs_hidden_node_tcp_failure`)

**New test**: Demonstrates that TCP fails in hidden node scenarios due to missing ACK path.

**Why TCP fails**:
- Forward path (node2 → node1): SINR=31.7 dB ✅ (data packets arrive)
- Return path (node1 → node2): SINR=-4.3 dB ❌ (ACK packets dropped)
- TCP requires bidirectional communication for handshake, data ACKs, and window updates

**Validates**:
- ✓ TCP connection hangs or times out
- ✓ Very low throughput (<10 Mbps) if connection partially succeeds
- ✓ Demonstrates why bidirectional protocols fail in hidden node scenarios

**Example output**:
```
Hidden Node TCP Test (Should Fail)
======================================================================
Test: node2 → node1 (TCP)
  Forward path: SINR=31.7 dB ✅
  Return path: SINR=-4.3 dB ❌ (ACKs cannot reach sender)
  Expected: Connection hangs or very low throughput (<10 Mbps)

  ✓ TCP failed as expected: Command 'docker exec clab-csma-mcs-test-node2 iperf3 -c 192.168.100.1 -t 8 -J' returned non-zero exit status 1

✓ TCP failure confirmed (hidden node breaks bidirectional protocols)
======================================================================
```

### 3. ✅ UDP Success Test (`test_csma_mcs_hidden_node_udp_success`)

**New test**: Demonstrates that UDP succeeds in hidden node scenarios (one-way traffic only).

**Why UDP succeeds**:
- Forward path (node2 → node1): SINR=31.7 dB ✅ (data packets arrive)
- Return path: Not needed (UDP has no ACKs)
- UDP is connectionless: no handshake, no ACKs, pure one-way data flow

**Validates**:
- ✓ UDP achieves high throughput (180-250 Mbps)
- ✓ Only forward path SINR matters for UDP
- ✓ Demonstrates protocol-specific behavior in hidden node scenarios

**Example output**:
```
Hidden Node UDP Test (Should Succeed)
======================================================================
Test: node2 → node1 (UDP)
  Forward path: SINR=31.7 dB ✅ (data packets arrive)
  Return path: Not needed (UDP has no ACKs)
  Expected: 180-220 Mbps (high SINR → low loss)

  Measured: 215.32 Mbps
  ✓ UDP succeeded (one-way protocol works with forward path only)

✓ UDP success confirmed!
  TCP: FAILS (needs bidirectional, return path broken)
  UDP: SUCCEEDS (one-way only, forward path works)
  Throughput: 215.32 Mbps
======================================================================
```

**Key takeaway**: The TCP vs UDP tests clearly demonstrate why protocol selection matters in hidden node scenarios. TCP's requirement for bidirectional communication makes it vulnerable to asymmetric link failures, while UDP's one-way nature allows it to work when only the forward path is viable.

### 4. ✅ Ping Connectivity (`test_csma_mcs_hidden_node_problem`)

**Validates**:
- ✓ node2 ↔ node3 connectivity works (both directions have positive SINR)
- ✓ All paths involving node1 FAIL (negative SINR for node1's TX, return path fails for pings TO node1)
- ✓ Selective connectivity matches SINR predictions

### 5. ✅ TC Configuration (`test_csma_mcs_tc_config`)

**Validates**:
- ✓ Rate limits match MCS-computed values
- ✓ Loss percentages match SINR-based PER
- ✓ Per-destination tc flower filters configured correctly

## Running the Tests

```bash
# Start channel server (in one terminal)
uv run sine channel-server

# Run all CSMA MCS tests (in another terminal)
UV_PATH=$(which uv) sudo -E $(which uv) run pytest -s \
    tests/integration/shared_bridge/sionna_engine/sinr/test_csma_mcs_comprehensive.py \
    -v -m integration

# Run specific tests
# TCP failure test (demonstrates bidirectional protocol issue)
UV_PATH=$(which uv) sudo -E $(which uv) run pytest -s \
    tests/integration/shared_bridge/sionna_engine/sinr/test_csma_mcs_comprehensive.py::test_csma_mcs_hidden_node_tcp_failure \
    -v

# UDP success test (demonstrates one-way protocol works)
UV_PATH=$(which uv) sudo -E $(which uv) run pytest -s \
    tests/integration/shared_bridge/sionna_engine/sinr/test_csma_mcs_comprehensive.py::test_csma_mcs_hidden_node_udp_success \
    -v

# Run TCP and UDP tests together to see the contrast
UV_PATH=$(which uv) sudo -E $(which uv) run pytest -s \
    tests/integration/shared_bridge/sionna_engine/sinr/test_csma_mcs_comprehensive.py::test_csma_mcs_hidden_node_tcp_failure \
    tests/integration/shared_bridge/sionna_engine/sinr/test_csma_mcs_comprehensive.py::test_csma_mcs_hidden_node_udp_success \
    -v
```

## Manual Testing with iperf3

```bash
# Deploy topology
UV_PATH=$(which uv) sudo -E $(which uv) run sine deploy \
    examples/for_tests/shared_sionna_sinr_csma-mcs/network.yaml

# Test 1: node1 → node2 (should fail, ~0 Mbps)
docker exec -d clab-csma-mcs-test-node2 iperf3 -s
docker exec clab-csma-mcs-test-node1 iperf3 -c 192.168.100.2 -t 10
# Expected: Connection fails or ~0 Mbps (100% loss)

# Test 2: node2 → node1 (should succeed, ~350-384 Mbps)
docker exec -d clab-csma-mcs-test-node1 iperf3 -s
docker exec clab-csma-mcs-test-node2 iperf3 -c 192.168.100.1 -t 10
# Expected: 350-384 Mbps (high MCS due to SINR=31.7 dB)

# Test 3: node2 ↔ node3 (both work, 128-192 Mbps)
docker exec -d clab-csma-mcs-test-node3 iperf3 -s
docker exec clab-csma-mcs-test-node2 iperf3 -c 192.168.100.3 -t 10
# Expected: ~192 Mbps (MCS 4, SINR=17.3 dB)

docker exec -d clab-csma-mcs-test-node2 iperf3 -s
docker exec clab-csma-mcs-test-node3 iperf3 -c 192.168.100.2 -t 10
# Expected: ~128 Mbps (MCS 3, SINR=14.8 dB)

# Cleanup
UV_PATH=$(which uv) sudo -E $(which uv) run sine destroy \
    examples/for_tests/shared_sionna_sinr_csma-mcs/network.yaml
```

## Key Takeaways

1. **SINR-based MCS selection is CRITICAL** for interference-limited scenarios
2. **Hidden node problem** causes asymmetric connectivity (can RX but not TX)
3. **Negative SINR is possible** when interference > signal power
4. **SNR asymmetry ≠ SINR asymmetry**: Path loss is symmetric, but interference is not
5. **Geometry matters**: Closer interferer = stronger interference = lower SINR
6. **Throughput tests are essential**: Ping tests alone don't reveal the full story

## References

- WiFi 6 MCS table: [examples/common_data/wifi6_mcs.csv](../../common_data/wifi6_mcs.csv)
- CSMA model: [src/sine/channel/csma_model.py](../../../src/sine/channel/csma_model.py)
- SINR computation: [src/sine/channel/interference_engine.py](../../../src/sine/channel/interference_engine.py)
- Integration tests: [tests/integration/shared_bridge/sionna_engine/sinr/test_csma_mcs_comprehensive.py](../../../tests/integration/shared_bridge/sionna_engine/sinr/test_csma_mcs_comprehensive.py)
