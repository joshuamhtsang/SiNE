# MANET Shared Bridge with SINR/Interference (Phase 2)

This example demonstrates a 3-node MANET with shared broadcast domain and **SINR computation with adjacent-channel interference**.

## Assumptions

This example assumes **Phase 2 of PLAN_SINR.md** is implemented:
- Adjacent-channel interference modeling
- ACLR (Adjacent-Channel Leakage Ratio) rejection per IEEE 802.11ax-2021
- Multi-frequency support in interference engine

If Phase 2 is not yet implemented, this example will fail with an error about missing SINR support or ACLR calculation.

## Topology

```
        node1 (5.18 GHz)
          /        \
         /          \
   node2 (5.20 GHz)--node3 (5.26 GHz)

- 30m equilateral triangle
- Free space (vacuum.xml scene)
- Mixed frequencies to test ACLR rejection
```

## Frequency Assignment

| Node | Frequency | Channel | Separation from node1 | ACLR Rejection |
|------|-----------|---------|----------------------|----------------|
| node1 | 5.18 GHz | Ch 36 | 0 MHz (reference) | N/A |
| node2 | 5.20 GHz | Ch 40 | 20 MHz (1st adjacent) | 28 dB |
| node3 | 5.26 GHz | Ch 52 | 80 MHz (2nd adjacent) | 40 dB |

## Expected SINR Behavior

### Link node1 ↔ node2 (Adjacent Channel)

- **Frequency separation**: 20 MHz (1st adjacent channel)
- **ACLR rejection**: 28 dB (per IEEE 802.11ax)
- **SNR**: ~35 dB (30m free space)
- **Interference from node3**:
  - Raw interference power: ~-65 dBm (30m path loss)
  - After ACLR: ~-93 dBm (-65 - 28 dB)
  - Impact on SINR: ~2-3 dB degradation
- **Expected SINR**: ~32-33 dB

### Link node1 ↔ node3 (2nd Adjacent Channel)

- **Frequency separation**: 80 MHz (2nd adjacent)
- **ACLR rejection**: 40 dB
- **SNR**: ~35 dB
- **Interference from node2**:
  - Raw interference power: ~-65 dBm
  - After ACLR: ~-105 dBm (-65 - 40 dB)
  - Impact on SINR: <1 dB (negligible)
- **Expected SINR**: ~34.5 dB

### Link node2 ↔ node3 (60 MHz separation)

- **Frequency separation**: 60 MHz (2nd adjacent)
- **ACLR rejection**: 40 dB
- **Expected SINR**: ~34.5 dB

## Expected Deployment Output

```
Deployment Summary:
  Link: node1→node2 [wireless, SINR enabled]
    SNR: 35.2 dB | SINR: 32.8 dB | Interferers: 1 (node3, ACLR: -28 dB)
    Expected interference: -93 dBm (after ACLR)
    Delay: 0.10 ms | Jitter: 0.00 ms | Loss: 0.00% | Rate: 192 Mbps

  Link: node2→node1 [wireless, SINR enabled]
    SNR: 35.2 dB | SINR: 32.8 dB | Interferers: 1 (node3, ACLR: -28 dB)
    Delay: 0.10 ms | Jitter: 0.00 ms | Loss: 0.00% | Rate: 192 Mbps

  Link: node1→node3 [wireless, SINR enabled]
    SNR: 35.2 dB | SINR: 34.5 dB | Interferers: 1 (node2, ACLR: -40 dB)
    Expected interference: -105 dBm (after ACLR)
    Delay: 0.10 ms | Jitter: 0.00 ms | Loss: 0.00% | Rate: 192 Mbps

  Link: node3→node1 [wireless, SINR enabled]
    SNR: 35.2 dB | SINR: 34.5 dB | Interferers: 1 (node2, ACLR: -40 dB)
    Delay: 0.10 ms | Jitter: 0.00 ms | Loss: 0.00% | Rate: 192 Mbps

  Link: node2→node3 [wireless, SINR enabled]
    SNR: 35.2 dB | SINR: 34.5 dB | Interferers: 1 (node1, ACLR: -40 dB)
    Delay: 0.10 ms | Jitter: 0.00 ms | Loss: 0.00% | Rate: 192 Mbps

  Link: node3→node2 [wireless, SINR enabled]
    SNR: 35.2 dB | SINR: 34.5 dB | Interferers: 1 (node1, ACLR: -40 dB)
    Delay: 0.10 ms | Jitter: 0.00 ms | Loss: 0.00% | Rate: 192 Mbps
```

## Validation Checks

1. **SINR < SNR**: Interference is present (SINR degradation from SNR)
2. **Adjacent channel degradation**: ~2-3 dB (28 dB ACLR, 1st adjacent)
3. **2nd adjacent degradation**: <1 dB (40 dB ACLR, nearly negligible)
4. **Throughput**: ~182-192 Mbps per link (high SINR still allows max rate)

## Deployment

```bash
# Start channel server
uv run sine channel-server

# Deploy (in another terminal)
sudo $(which uv) run sine deploy examples/manet_triangle_shared_sinr/network.yaml

# Test connectivity
docker exec clab-sh-sio-sinr-equal-triangle-node1 ping -c 3 192.168.100.2
docker exec clab-sh-sio-sinr-equal-triangle-node1 ping -c 3 192.168.100.3

# Test throughput (node1 → node2)
docker exec -d clab-sh-sio-sinr-equal-triangle-node1 iperf3 -s
docker exec clab-sh-sio-sinr-equal-triangle-node2 iperf3 -c 192.168.100.1 -t 10

# Cleanup
sudo $(which uv) run sine destroy examples/manet_triangle_shared_sinr/network.yaml
```

## Comparison with No-SINR Example

| Metric | manet_triangle_shared (no SINR) | manet_triangle_shared_sinr (Phase 2) |
|--------|----------------------------------|--------------------------------------|
| **Interference model** | None (SNR-only) | Adjacent-channel (ACLR) |
| **SNR** | ~35 dB | ~35 dB |
| **SINR** | N/A (SNR used directly) | ~32-34.5 dB (varies by frequency sep) |
| **Throughput** | ~182-192 Mbps | ~182-192 Mbps (high SINR maintains rate) |
| **Use case** | Simple free-space testing | Realistic multi-frequency MANET |

## Key Differences from Phase 1.5 (CSMA) Example

This example tests **Phase 2 (ACLR)**, not Phase 1.5 (CSMA/CA):

| Feature | Phase 1.5 (CSMA) | Phase 2 (ACLR) - This Example |
|---------|------------------|-------------------------------|
| **MAC model** | CSMA/CA statistical (carrier sensing) | N/A (Phase 2 is PHY-layer only) |
| **Frequency model** | Co-channel only | Multi-frequency with ACLR |
| **Interference calculation** | Expected interference (Pr[TX] × I) | Full interference with frequency rejection |
| **Key validation** | SINR improvement from spatial reuse | Graded interference by frequency separation |

## Troubleshooting

### Error: "SINR computation not supported"

Phase 2 is not yet implemented. Wait for SINR implementation (see PLAN_SINR.md).

### Error: "ACLR calculation not found"

Phase 2's ACLR rejection model is missing. Check that `src/sine/channel/sinr.py` has `calculate_aclr_wifi6()` method.

### Unexpected: SINR = SNR

If SINR equals SNR exactly, interference is not being computed. Check:
1. `enable_sinr: true` in network.yaml
2. Frequency differences are non-zero
3. All nodes are active (transmission state)

### Low throughput (<150 Mbps)

If throughput is significantly below 182 Mbps:
1. Check SINR values (should be >30 dB for 64-QAM)
2. Verify netem rate limits are applied correctly
3. Check for packet loss (should be ~0%)

## IEEE 802.11ax ACLR Reference

Per IEEE 802.11ax-2021 Section 27.3.21 (Transmit spectrum mask):

| Frequency Offset | Spectral Mask Requirement | ACLR (dB) |
|------------------|---------------------------|-----------|
| 0 to ±10 MHz | 0 dBr (in-band) | 0 |
| ±10 to ±20 MHz | -20 dBr | 20 |
| ±20 to ±30 MHz | -28 dBr | 28 |
| ±30 to ±40 MHz | -40 dBr | 40 |
| >±40 MHz | <-40 dBr | 45 (typical) |

SiNE uses conservative values (28, 40, 45 dB) matching the spec requirements.
