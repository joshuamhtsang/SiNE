# CSMA + Adaptive MCS Integration Test - Linear Topology

This example validates that **MCS selection uses SINR (not SNR)** when a CSMA MAC model is present, ensuring interference is properly accounted for in modulation selection.

## Topology

Linear arrangement demonstrating interference-limited scenario:

```
node1 ──────── node2 ──────── node3
(0,0,1)      (20,0,1)      (40,0,1)
```

**Distances:**
- node1 ↔ node2: 20m
- node2 ↔ node3: 20m (primary test link)
- node1 ↔ node3: 40m

## Expected Behavior

**Link node2 → node3** (primary test link):
- **Signal power**: -52.7 dBm (from node2 @ 20m)
- **Interference**: -64.0 dBm effective (from node1 @ 40m, 30% traffic load)
- **Noise floor**: -95.0 dBm
- **SNR**: 42.2 dB (signal-to-noise, without interference)
- **SINR**: 11.3 dB (**interference-limited!** I >> N)
- **Degradation**: 31 dB (demonstrates massive interference impact)

**MCS Selection:**
- **Without fix**: MCS selected on SNR=42 dB → MCS 10-11 (1024-QAM) ❌
- **With fix**: MCS selected on SINR=11 dB → MCS 2-3 (QPSK/16-QAM) ✓

This demonstrates the **CRITICAL IMPORTANCE** of using SINR for MCS selection in interference-limited scenarios!

## Key Validations

The integration test `test_csma_mcs_uses_sinr()` checks:

1. ✓ **SINR << SNR** (interference dominates)
2. ✓ **MCS selection uses SINR** (low MCS for SINR≈11 dB, not high MCS for SNR≈42 dB)
3. ✓ **MAC model type** is "csma"
4. ✓ **SINR degradation** is large (20-35 dB) due to strong interference
5. ✓ **Interference-limited regime** (I >> N)

## Without SINR Fix (Bug)

- MCS selected on **SNR=42 dB** → MCS 10 or 11 (1024-QAM)
- Ignores 31 dB interference degradation
- Will cause **massive packet loss** (wrong modulation for channel conditions)
- Throughput will be near zero

## With SINR Fix (Correct)

- MCS selected on **SINR=11 dB** → MCS 2 (QPSK rate-0.75)
- Accounts for interference from node1
- Robust link with ~1% packet loss
- Throughput ~72 Mbps (realistic for channel conditions)

## Deployment

```bash
# Start channel server (in one terminal)
uv run sine channel-server

# Deploy with mobility API (in another terminal)
sudo $(which uv) run sine deploy --enable-mobility examples/csma_mcs_test/network.yaml

# Run integration test
sudo -v && uv run pytest tests/integration/test_mac_throughput.py::test_csma_mcs_uses_sinr -v -s -m integration

# Cleanup
sudo $(which uv) run sine destroy examples/csma_mcs_test/network.yaml
```

## Expected Deployment Output

```
Link Parameters:
  node2:eth1 ↔ node3:eth1 [wireless]
    SNR: 42.2 dB | SINR: 11.3 dB (interference-limited) [CSMA]
    MCS: 2 (selected on SINR, qpsk rate-0.75 ldpc)
    Delay: 0.07 ms | Jitter: 0.00 ms | Loss: ~1% | Rate: ~72 Mbps
```

## Testing with iperf3

```bash
# Configure IPs (already done by deployment)
# node1: 192.168.100.1/24
# node2: 192.168.100.2/24
# node3: 192.168.100.3/24

# Start iperf3 server on node3
docker exec -d clab-csma-mcs-test-node3 iperf3 -s

# Run iperf3 client from node2 to node3
docker exec clab-csma-mcs-test-node2 iperf3 -c 192.168.100.3 -t 30

# Expected: ~68-72 Mbps (matching MCS 2 rate for SINR=11 dB)
# Compare to SNR-based MCS 10 (would expect 500+ Mbps but fail due to interference)
```

## References

- WiFi 6 MCS table: [examples/wifi6_adaptive/data/wifi6_mcs.csv](../wifi6_adaptive/data/wifi6_mcs.csv)
- CSMA model: [src/sine/channel/csma_model.py](../../src/sine/channel/csma_model.py)
- Integration test: [tests/integration/test_mac_throughput.py](../../tests/integration/test_mac_throughput.py)
