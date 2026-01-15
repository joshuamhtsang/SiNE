# Shared Bridge Testing Guide

This directory contains comprehensive validation tests for the shared bridge (true broadcast medium) implementation in SiNE.

## Test Scripts

| Script | Purpose | What It Tests |
|--------|---------|---------------|
| `test_tc_config.sh` | TC configuration verification | HTB hierarchy, classes, qdiscs, flower filters |
| `test_ping_rtt.sh` | Ping RTT validation | Per-destination delays match expected values |
| `test_filter_stats.sh` | Filter statistics verification | Flower filters correctly classify packets |
| `run_all_tests.sh` | Comprehensive test runner | Runs all tests and provides summary |

## Quick Start

### Option 1: Test Existing Deployment

If you already have the topology deployed:

```bash
# Run all tests
./run_all_tests.sh
```

### Option 2: Deploy and Test

To deploy the topology and run all tests in one command:

```bash
# Deploy and test
./run_all_tests.sh --deploy
```

**Note:** The `--deploy` option will automatically:
1. Start the channel server
2. Deploy the topology
3. Run all tests
4. Clean up on exit (Ctrl+C or test completion)

## Individual Tests

### Test 1: TC Configuration Verification

**What it tests:**
- HTB root qdisc exists with correct default class (99)
- Parent class (1:1) is configured
- Per-destination classes (1:10, 1:20, ...) exist for each peer
- Netem qdiscs are attached to each class
- Flower filters use `dst_ip` matching for O(1) classification

**Run:**
```bash
./test_tc_config.sh
```

**Expected output:**
```
✓ node1: HTB root qdisc present
✓ node1: Default class 99 configured
✓ node1: Parent class 1:1 present
✓ node1: 2 per-destination classes (expected 2)
✓ node1: 3 netem qdiscs (expected 3)
✓ node1: 2 flower filters (expected 2)
✓ node1: Flower filters use dst_ip matching
```

**What success means:**
- All nodes have correct HTB + flower filter configuration
- Per-destination netem is properly applied
- Broadcast traffic will use default class (minimal delay)

### Test 2: Ping RTT Validation

**What it tests:**
- Ping RTT ≈ 2× configured one-way delay
- All node pairs can communicate
- Per-destination delays are being applied

**Run:**
```bash
./test_ping_rtt.sh
```

**Expected output:**
```
✓ node1 → node2 (192.168.100.2):
    Expected RTT: 0.066 ms (2× 0.033 ms delay)
    Actual RTT:   0.068 ms
    Difference:   3%

✓ node1 → node3 (192.168.100.3):
    Expected RTT: 0.058 ms (2× 0.029 ms delay)
    Actual RTT:   0.062 ms
    Difference:   6.9%
```

**Tolerance:**
- ±20% difference is acceptable (accounts for processing overhead, jitter)
- Larger differences may indicate issues or asymmetric delays

**What success means:**
- Netem delays are being applied correctly
- RTT reflects configured channel conditions
- No major routing or configuration issues

### Test 3: Filter Statistics Verification

**What it tests:**
- Flower filters are matching packets
- Packets are being classified to correct destinations
- Qdiscs are processing packets through netem

**Run:**
```bash
./test_filter_stats.sh
```

**Expected output:**
```
Generating test traffic (100 pings per pair)...
  node1 → node2: 100 packets sent
  node1 → node3: 100 packets sent
  ...

node1 → node2 (192.168.100.2):
  Filter matched: 200 packets
  Qdisc processed: 200 packets
  ✓ Filter is classifying packets
  ✓ Qdisc is processing packets
```

**What success means:**
- Flower filters are correctly identifying destination IPs
- Packets are being routed through correct netem qdiscs
- Per-destination channel conditions are being applied

## Manual Verification Commands

### View TC Configuration

```bash
# View all qdiscs on node1
docker exec clab-manet-triangle-shared-node1 tc qdisc show dev eth1

# View all classes on node1
docker exec clab-manet-triangle-shared-node1 tc class show dev eth1

# View all filters on node1
docker exec clab-manet-triangle-shared-node1 tc filter show dev eth1

# View detailed statistics
docker exec clab-manet-triangle-shared-node1 tc -s qdisc show dev eth1
docker exec clab-manet-triangle-shared-node1 tc -s class show dev eth1
docker exec clab-manet-triangle-shared-node1 tc -s filter show dev eth1
```

### Manual Ping Tests

```bash
# Ping from node1 to node2
docker exec clab-manet-triangle-shared-node1 ping -c 10 192.168.100.2

# Ping from node1 to node3
docker exec clab-manet-triangle-shared-node1 ping -c 10 192.168.100.3

# Ping all pairs
for src in node1 node2 node3; do
    for dst in node1 node2 node3; do
        if [ "$src" != "$dst" ]; then
            echo "=== $src → $dst ==="
            docker exec "clab-manet-triangle-shared-$src" ping -c 5 "192.168.100.${dst: -1}"
        fi
    done
done
```

### Check Filter Match Statistics

```bash
# Watch filter statistics in real-time
watch -n 1 'docker exec clab-manet-triangle-shared-node1 tc -s filter show dev eth1'

# Generate traffic and observe packet counts
docker exec clab-manet-triangle-shared-node1 ping -c 100 -i 0.01 192.168.100.2 &
docker exec clab-manet-triangle-shared-node1 tc -s filter show dev eth1 | grep -A5 "dst_ip 192.168.100.2"
```

## Expected TC Configuration

For a 3-node topology, each node should have:

### Qdiscs (4 total per node)

```
qdisc htb 1: root refcnt 2 default 99
qdisc netem 99: parent 1:99 delay 1.0ms
qdisc netem 10: parent 1:10 delay X.XXXms
qdisc netem 20: parent 1:20 delay Y.YYYms
```

### Classes (4 total per node)

```
class htb 1:1 parent 1: rate 1Gbit ceil 1Gbit
class htb 1:99 parent 1:1 rate 1Gbit ceil 1Gbit
class htb 1:10 parent 1:1 rate XXXmbit ceil XXXmbit
class htb 1:20 parent 1:1 rate YYYmbit ceil YYYmbit
```

### Filters (2 total per node)

```
filter protocol ip pref 1 flower chain 0 handle 0x1
  dst_ip 192.168.100.2
  action pass flowid 1:10

filter protocol ip pref 1 flower chain 0 handle 0x2
  dst_ip 192.168.100.3
  action pass flowid 1:20
```

## Troubleshooting

### Test Failures

#### TC Configuration Test Fails

**Symptom:** Missing HTB qdisc or classes

**Causes:**
- Deployment failed or didn't complete
- netem configuration error
- Insufficient sudo permissions

**Fix:**
```bash
# Redeploy
sudo $(which uv) run sine destroy examples/manet_triangle_shared/network.yaml
sudo $(which uv) run sine deploy examples/manet_triangle_shared/network.yaml
```

#### Ping RTT Test Fails

**Symptom:** Actual RTT differs significantly from expected

**Causes:**
- Container CPU throttling
- Network namespace overhead
- Asymmetric channel conditions (different TX/RX delays)

**Debug:**
```bash
# Check if delay is being applied
docker exec clab-manet-triangle-shared-node1 tc qdisc show dev eth1 | grep netem

# Verify flower filter is matching
docker exec clab-manet-triangle-shared-node1 tc -s filter show dev eth1

# Check for packet drops
docker exec clab-manet-triangle-shared-node1 tc -s qdisc show dev eth1 | grep dropped
```

#### Filter Statistics Test Fails

**Symptom:** Filter matched 0 packets

**Causes:**
- Flower filter not installed (kernel < 4.2)
- Incorrect IP addresses in filters
- Traffic not reaching interface

**Debug:**
```bash
# Check kernel version (must be >= 4.2)
uname -r

# Verify flower support
tc filter add dev lo flower help 2>&1 | grep -q "flower" && echo "Supported"

# Check IP addresses
docker exec clab-manet-triangle-shared-node1 ip addr show eth1

# Verify filters match configured IPs
docker exec clab-manet-triangle-shared-node1 tc filter show dev eth1
```

### Common Issues

#### "Container not found" Error

**Cause:** Topology not deployed

**Fix:**
```bash
sudo $(which uv) run sine deploy examples/manet_triangle_shared/network.yaml
```

#### "Permission denied" Error

**Cause:** Tests require sudo for `docker exec`

**Fix:** Run tests with appropriate permissions or add user to docker group

#### Ping Shows 100% Packet Loss

**Cause:** IP addresses not applied or routing issue

**Fix:**
```bash
# Verify IPs
for node in node1 node2 node3; do
    echo "=== $node ==="
    docker exec "clab-manet-triangle-shared-$node" ip addr show eth1
done

# Redeploy if IPs missing
sudo $(which uv) run sine destroy examples/manet_triangle_shared/network.yaml
sudo $(which uv) run sine deploy examples/manet_triangle_shared/network.yaml
```

## Performance Benchmarks

### Expected Test Runtime

| Test | Duration |
|------|----------|
| TC Configuration | ~5 seconds |
| Ping RTT | ~20 seconds |
| Filter Statistics | ~30 seconds (100 pings × 6 pairs) |
| **Total** | **~55 seconds** |

### Resource Usage

| Resource | Usage |
|----------|-------|
| CPU | < 5% per container during tests |
| Memory | ~50 MB per container |
| Network | ~1 Mbps during ping tests |

## Test Coverage

- ✅ HTB qdisc configuration
- ✅ HTB class hierarchy
- ✅ Netem qdisc attachment
- ✅ Flower filter installation
- ✅ Per-destination delay application
- ✅ Packet classification accuracy
- ✅ End-to-end connectivity
- ✅ RTT accuracy

## Future Tests (Not Yet Implemented)

- MANET routing protocol testing (OLSR, BATMAN-adv, Babel)
- Throughput validation with iperf3
- Packet loss verification
- Broadcast/multicast traffic handling
- Mobility scenario testing
- Large-scale topology testing (10+ nodes)

## CI/CD Integration

To integrate these tests into CI/CD:

```yaml
# Example GitHub Actions workflow
- name: Deploy SiNE Shared Bridge
  run: |
    sudo $(which uv) run sine channel-server &
    sleep 3
    sudo $(which uv) run sine deploy examples/manet_triangle_shared/network.yaml

- name: Run Validation Tests
  run: |
    cd examples/manet_triangle_shared
    ./run_all_tests.sh

- name: Cleanup
  if: always()
  run: |
    sudo $(which uv) run sine destroy examples/manet_triangle_shared/network.yaml
```

## References

- [Linux TC Documentation](https://man7.org/linux/man-pages/man8/tc.8.html)
- [HTB Guide](https://luxik.cdi.cz/~devik/qos/htb/)
- [Flower Filter Documentation](https://man7.org/linux/man-pages/man8/tc-flower.8.html)
- [Netem Documentation](https://man7.org/linux/man-pages/man8/tc-netem.8.html)
