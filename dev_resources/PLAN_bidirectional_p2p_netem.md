# Implementation Plan: Bidirectional P2P Wireless Links with Asymmetric Netem

## Executive Summary

**Decision: IMPLEMENT bidirectional computation for P2P wireless links**

Both the wireless communications engineer and Linux networking specialist strongly recommend this change:

- ✅ **Physically correct**: Noise figure is a receiver property; different NF values produce asymmetric SNR
- ✅ **Significant impact**: 3-9 dB SNR differences lead to 14% throughput differences in WiFi 6 scenarios
- ✅ **Protocol realism**: Critical for MANET routing (OLSR, AODV) and TCP ACK path modeling
- ✅ **Architecturally sound**: Matches existing fixed link implementation pattern
- ✅ **Low risk**: Minimal code changes, easy to test, no breaking changes

**Current behavior (INCORRECT):**
- Computes channel once: node1→node2 using node2's RX noise figure
- Applies same netem params to both interfaces (symmetric)
- Reverse direction not computed independently

**Proposed behavior (CORRECT):**
- Compute channel twice per link:
  - Direction A→B: Uses receiver B's noise figure → params_ab
  - Direction B→A: Uses receiver A's noise figure → params_ba
- Apply different netem params to each interface based on egress direction
- Each direction correctly models its receiver's characteristics

**Estimated effort:** 5-9 hours (low complexity, high impact)

---

## Scope Clarification: P2P vs Shared Bridge Models

### CRITICAL: This Plan Only Affects Point-to-Point (P2P) Links

**Your concern about one interface communicating with multiple destinations is valid - but it only applies to shared bridge mode, which ALREADY handles this correctly with tc flower filters!**

### Two Distinct Network Models in SiNE

| Aspect | Point-to-Point (P2P) | Shared Bridge (Broadcast) |
|--------|---------------------|--------------------------|
| **Interfaces per node** | N-1 interfaces for N nodes | Single interface per node |
| **Example (3 nodes)** | node1 has eth1, eth2, eth3 | node1 has only eth1 |
| **Connectivity** | eth1→peer1, eth2→peer2, eth3→peer3 | eth1→bridge (all peers) |
| **Netem application** | One qdisc per interface | HTB + tc flower filters |
| **Per-destination support** | N/A (each interface = one peer) | ✅ Per-destination filters |
| **This plan affects** | ✅ YES (bidirectional) | ❌ NO (already correct) |

### Point-to-Point Model (What This Plan Modifies)

**Architecture:**
```
node1 (position A)
 ├── eth1 → veth → node2:eth1 (position B)
 ├── eth2 → veth → node3:eth1 (position C)
 └── eth3 → veth → node4:eth1 (position D)
```

**Netem application per link:**
- `node1:eth1` has netem for node1→node2 link (uses node2's RX NF)
- `node1:eth2` has netem for node1→node3 link (uses node3's RX NF)
- `node1:eth3` has netem for node1→node4 link (uses node4's RX NF)

**No conflict because each interface talks to exactly ONE peer.**

**Topology example:** Point-to-point links require explicit `links` section:
```yaml
topology:
  nodes: [node1, node2, node3]
  links:
    - endpoints: [node1:eth1, node2:eth1]  # Dedicated interface pair
    - endpoints: [node1:eth2, node3:eth1]  # Separate interface pair
    - endpoints: [node2:eth2, node3:eth2]  # Another interface pair
```

### Shared Bridge Model (NOT Modified - Already Correct)

**Architecture:**
```
node1:eth1 ────┐
               ├──── bridge (manet-br0)
node2:eth1 ────┤
               │
node3:eth1 ────┘

All nodes communicate via SINGLE interface (eth1) connected to shared bridge.
```

**The problem you identified:** How does `node1:eth1` apply different netem to packets going to node2 vs node3 when both use the same interface?

**The solution (already implemented):** Per-destination tc flower filters!

**File:** [src/sine/topology/shared_netem.py](src/sine/topology/shared_netem.py)

```bash
# On node1:eth1, create HTB hierarchy with per-destination classes:

# 1. Root HTB qdisc
tc qdisc add dev eth1 root handle 1: htb default 99

# 2. Parent class (unlimited rate)
tc class add dev eth1 parent 1: classid 1:1 htb rate 1gbit

# 3. Per-destination classes with netem as child qdisc
tc class add dev eth1 parent 1:1 classid 1:10 htb rate 1gbit
tc qdisc add dev eth1 parent 1:10 handle 10: netem delay 5ms loss 0.1%  # To node2

tc class add dev eth1 parent 1:1 classid 1:20 htb rate 1gbit
tc qdisc add dev eth1 parent 1:20 handle 20: netem delay 10ms loss 0.5%  # To node3

# 4. Flower filters to classify packets by destination IP
tc filter add dev eth1 parent 1: protocol ip prio 1 \
    flower dst_ip 192.168.100.2 flowid 1:10  # Packets to node2 use class 1:10

tc filter add dev eth1 parent 1: protocol ip prio 1 \
    flower dst_ip 192.168.100.3 flowid 1:20  # Packets to node3 use class 1:20

# 5. Default class for broadcast/multicast
tc class add dev eth1 parent 1:1 classid 1:99 htb rate 1gbit
tc qdisc add dev eth1 parent 1:99 handle 99: netem delay 0ms loss 0%
```

**Result:** Single interface (`node1:eth1`) can have different netem parameters per destination IP address!

**Topology example:** `examples/manet_triangle_shared/network.yaml`
```yaml
topology:
  shared_bridge:
    enabled: true
    name: manet-br0
    nodes: [node1, node2, node3]
    interface_name: eth1  # All nodes use eth1 for shared broadcast

  nodes:
    node1:
      interfaces:
        eth1:  # Only ONE interface, talks to all peers via bridge
          ip_address: 192.168.100.1/24
          wireless: {...}
```

**Channel computation:** Already bidirectional! [controller.py:276-297](src/sine/emulation/controller.py#L276-L297)
```python
# Compute all-to-all directional links
for tx_node in nodes:
    for rx_node in nodes:
        if tx_node == rx_node:
            continue
        # Compute tx_node → rx_node (uses rx_node's NF)
        # Store in per-destination netem params
```

**Shared bridge already implements bidirectional computation with correct per-receiver NF!**

### Why This Plan Only Affects P2P Mode

| Question | Answer |
|----------|--------|
| Does P2P have one interface per peer? | ✅ Yes - no multi-destination problem |
| Does P2P compute bidirectionally? | ❌ No (current) - this is what we're fixing |
| Does shared bridge have one interface for all peers? | ✅ Yes - needs per-destination filters |
| Does shared bridge compute bidirectionally? | ✅ Yes (already) - uses correct RX NF per dest |
| Does shared bridge use tc flower filters? | ✅ Yes (already) - different netem per dest IP |

### Summary: Your Concern is Valid but Already Solved

**Your question:** "How do we handle cases where node1:eth1 talks to both node2 and node3 with different channel conditions?"

**Answer:**
- **P2P mode:** Doesn't happen - node1 uses `eth1` for node2 and `eth2` for node3 (separate interfaces)
- **Shared bridge mode:** Already solved with tc flower filters - single interface can have per-destination netem

**This plan:** Fixes P2P mode to compute bidirectionally (like shared bridge already does)

---

## Technical Approach

### Architecture Pattern (Mirrors Fixed Links)

Fixed links already implement this exact pattern in [controller.py:629-671](src/sine/emulation/controller.py#L629-L671):

```python
# Fixed links: Create separate params per endpoint
params1 = NetemParams(fixed1.delay_ms, fixed1.loss_percent, ...)
params2 = NetemParams(fixed2.delay_ms, fixed2.loss_percent, ...)

# Apply different params to each interface
self.netem_config.apply_config(..., params=params1)  # node1:iface1
self.netem_config.apply_config(..., params=params2)  # node2:iface2
```

Wireless links should follow the same pattern:

```python
# Proposed: Compute separate params for each direction
params1 = compute_channel(tx=node1, rx=node2)  # Uses node2's RX NF
params2 = compute_channel(tx=node2, rx=node1)  # Uses node1's RX NF

# Apply to each interface (same pattern as fixed links)
self.netem_config.apply_config(..., params=params1)  # node1:eth1 egress
self.netem_config.apply_config(..., params=params2)  # node2:eth1 egress
```

### Netem Egress Semantics (Linux Networking Specialist Confirmation)

- ✅ Netem on `node1:eth1` affects **egress traffic only** (packets leaving node1)
- ✅ Each interface can have independent netem configuration
- ✅ No conflicts between qdiscs on different interfaces
- ✅ Containerlab's bridge architecture is transparent to netem

This means applying different netem params to each endpoint correctly models asymmetric wireless channels.

---

## Implementation Steps

### Phase 1: Core Channel Computation Logic

**File:** `src/sine/emulation/controller.py`

**Function:** `_configure_wireless_link()` (currently lines 518-612)

**Changes:**

1. **Replace single channel computation with bidirectional:**

```python
# BEFORE (current - symmetric):
result = await self._compute_channel_request(
    tx_node=node1, rx_node=node2,  # Only one direction
    wireless1=wireless1, wireless2=wireless2,
    ...
)
params = NetemParams(result.delay_ms, result.loss_percent, ...)

# Apply same params to both interfaces
apply_netem(node1, iface1, params)  # Egress from node1
apply_netem(node2, iface2, params)  # Egress from node2 (WRONG - uses node2's NF)

# AFTER (proposed - bidirectional):
# Direction 1: node1 → node2 (egress from node1)
result_12 = await self._compute_channel_request(
    tx_node=node1, rx_node=node2,
    wireless1=wireless1, wireless2=wireless2,  # Uses node2's RX NF
    ...
)
params_12 = NetemParams(result_12.delay_ms, result_12.loss_percent, ...)
apply_netem(node1, iface1, params_12)  # Egress from node1

# Direction 2: node2 → node1 (egress from node2)
result_21 = await self._compute_channel_request(
    tx_node=node2, rx_node=node1,
    wireless1=wireless2, wireless2=wireless1,  # Uses node1's RX NF (SWAPPED)
    ...
)
params_21 = NetemParams(result_21.delay_ms, result_21.loss_percent, ...)
apply_netem(node2, iface2, params_21)  # Egress from node2
```

2. **Store link states for both directions:**

```python
# BEFORE: Single state
self._link_states[(node1, node2)] = {...}

# AFTER: Two directional states
self._link_states[(node1, node2)] = {
    "rf": {"snr_db": result_12.snr_db, ...},
    "netem": {"loss_percent": result_12.per * 100, ...}
}
self._link_states[(node2, node1)] = {
    "rf": {"snr_db": result_21.snr_db, ...},
    "netem": {"loss_percent": result_21.per * 100, ...}
}
```

**Optimization Option (Future):**
Cache path loss (symmetric) and only recompute SNR with different NF. This reduces overhead from 2× to ~1.1×. Implement later if performance becomes a concern.

### Phase 2: Deployment Summary Updates

**File:** `src/sine/emulation/controller.py`

**Function:** Deployment summary printing (search for "Link Parameters")

**Changes:**

Show both directions when they differ:

```python
# BEFORE (symmetric):
Link Parameters:
  node1:eth1 ↔ node2:eth1 [wireless]
    Delay: 0.07 ms | Loss: 0.10% | Rate: 192 Mbps

# AFTER (bidirectional - show both if asymmetric):
Link Parameters:
  node1:eth1 → node2:eth1 [wireless]
    SNR: 28.5 dB | Loss: 0.10% | Rate: 192 Mbps
  node2:eth1 → node1:eth1 [wireless]
    SNR: 31.5 dB | Loss: 0.01% | Rate: 467 Mbps

# For symmetric links (same NF), optionally show condensed format:
  node1:eth1 ↔ node2:eth1 [wireless, symmetric]
    SNR: 30.0 dB | Loss: 0.05% | Rate: 400 Mbps
```

**Decision point:** Verbose (always show both) or smart (detect symmetry)?
- **Recommendation:** Always show both for consistency and transparency

### Phase 3: Testing

**CRITICAL: Test both P2P and shared bridge modes to ensure no regressions**

#### Test 1: P2P Mode with Asymmetric NF (New Test)

**File:** `tests/integration/test_noise_figure_deployment.py`

**New Test:** `test_bidirectional_asymmetric_netem()`

```python
def test_bidirectional_asymmetric_netem(channel_server, temp_topology_dir):
    """
    Verify P2P links compute asymmetric netem based on each receiver's NF.

    Topology: node1 (NF=7dB) ↔ node2 (NF=10dB) at 20m

    Expected:
    - Direction node1→node2: Uses node2's NF=10dB → lower SNR → higher loss%
    - Direction node2→node1: Uses node1's NF=7dB → higher SNR → lower loss%
    - SNR difference: ~3 dB
    - Both directions stored in link_states
    """
    topology_file = create_vacuum_topology_asymmetric_nf(
        temp_topology_dir,
        node1_nf=7.0,   # WiFi 6 typical
        node2_nf=10.0,  # Cheap IoT radio
    )

    controller = EmulationController(topology_file)

    try:
        asyncio.run(controller.start())

        # Verify BOTH directional states exist
        link_ab = controller._link_states.get(("node1", "node2"))
        link_ba = controller._link_states.get(("node2", "node1"))

        assert link_ab is not None, "Forward link state missing"
        assert link_ba is not None, "Reverse link state missing"

        # Extract SNR values
        snr_ab = link_ab["rf"]["snr_db"]  # node1→node2 (uses NF=10dB)
        snr_ba = link_ba["rf"]["snr_db"]  # node2→node1 (uses NF=7dB)

        # Verify ~3 dB SNR difference
        snr_diff = snr_ba - snr_ab
        assert 2.5 < snr_diff < 3.5, (
            f"Expected ~3 dB SNR difference (NF difference), "
            f"got {snr_diff:.1f} dB (AB: {snr_ab:.1f} dB, BA: {snr_ba:.1f} dB)"
        )

        # Verify asymmetric loss rates
        loss_ab = link_ab["netem"]["loss_percent"]
        loss_ba = link_ba["netem"]["loss_percent"]

        # Higher NF → lower SNR → higher loss
        assert loss_ab > loss_ba, (
            f"Direction with worse NF should have higher loss, "
            f"got AB: {loss_ab:.3f}%, BA: {loss_ba:.3f}%"
        )

        # Verify delay is symmetric (same geometric path)
        delay_ab = link_ab["netem"]["delay_ms"]
        delay_ba = link_ba["netem"]["delay_ms"]
        assert abs(delay_ab - delay_ba) < 0.01, (
            f"Delay should be symmetric (same path), "
            f"got AB: {delay_ab} ms, BA: {delay_ba} ms"
        )

    finally:
        asyncio.run(controller.stop())
```

**Additional test updates:**
- Update `test_heterogeneous_noise_figures()` to verify both directions
- Ensure existing tests still pass (they should - no breaking changes)

#### Test 2: Shared Bridge Mode with Heterogeneous NF (Critical Regression Test)

**Purpose:** Verify that shared bridge mode still works correctly with per-destination tc flower filters and that bidirectional P2P changes don't break shared bridge functionality.

**Topology:** `examples/manet_triangle_shared/network.yaml` (modified with asymmetric NF)

**File:** `tests/integration/test_shared_bridge_asymmetric_nf.py` (new file)

```python
def test_shared_bridge_per_destination_netem(channel_server, temp_topology_dir):
    """
    Verify shared bridge mode correctly applies per-destination netem with asymmetric NF.

    Topology: 3-node triangle on shared bridge
    - node1: NF=7 dB (WiFi 6)
    - node2: NF=10 dB (IoT device)
    - node3: NF=5 dB (high-end base station)

    Expected behavior:
    1. Each node has ONE interface (eth1) connected to shared bridge
    2. Per-destination tc flower filters on each interface
    3. Different netem params per destination based on receiver's NF
    4. All 6 directional links (3 nodes × 2 directions) have correct params

    Example: node1:eth1 should have:
    - Packets to node2 (192.168.100.2): Uses node2's NF=10dB → higher loss
    - Packets to node3 (192.168.100.3): Uses node3's NF=5dB → lower loss
    """
    topology_file = create_manet_triangle_shared_asymmetric(
        temp_topology_dir,
        node1_nf=7.0,
        node2_nf=10.0,
        node3_nf=5.0,
    )

    controller = EmulationController(topology_file)

    try:
        asyncio.run(controller.start())

        # Verify all 6 directional link states exist
        expected_links = [
            ("node1", "node2"),
            ("node1", "node3"),
            ("node2", "node1"),
            ("node2", "node3"),
            ("node3", "node1"),
            ("node3", "node2"),
        ]

        for tx, rx in expected_links:
            link_state = controller._link_states.get((tx, rx))
            assert link_state is not None, f"Link state {tx}→{rx} missing"

        # Verify SNR differences based on receiver NF
        # node1→node2 (RX NF=10dB) vs node1→node3 (RX NF=5dB) should differ by 5dB
        snr_12 = controller._link_states[("node1", "node2")]["rf"]["snr_db"]
        snr_13 = controller._link_states[("node1", "node3")]["rf"]["snr_db"]

        snr_diff = snr_13 - snr_12  # node3 has better NF → higher SNR
        assert 4.5 < snr_diff < 5.5, (
            f"Expected ~5 dB SNR difference (NF: 10dB vs 5dB), "
            f"got {snr_diff:.1f} dB (to node2: {snr_12:.1f} dB, to node3: {snr_13:.1f} dB)"
        )

        # Verify tc flower filters are configured correctly
        # Check node1:eth1 has per-destination netem
        container_info = controller.containerlab_mgr.get_container_info("node1")
        pid = container_info["pid"]

        # Get tc filter list
        result = subprocess.run(
            ["nsenter", "-t", str(pid), "-n", "tc", "filter", "show", "dev", "eth1"],
            capture_output=True,
            text=True,
        )
        tc_output = result.stdout

        # Verify filters exist for node2 and node3 IP addresses
        assert "192.168.100.2" in tc_output, "Missing tc filter for node2"
        assert "192.168.100.3" in tc_output, "Missing tc filter for node3"

        # Verify HTB hierarchy exists
        result = subprocess.run(
            ["nsenter", "-t", str(pid), "-n", "tc", "qdisc", "show", "dev", "eth1"],
            capture_output=True,
            text=True,
        )
        qdisc_output = result.stdout
        assert "htb" in qdisc_output, "HTB qdisc not configured"
        assert "netem" in qdisc_output, "Netem not attached to HTB classes"

        logger.info("✅ Shared bridge per-destination netem verified")

    finally:
        asyncio.run(controller.stop())
```

**Why this test is critical:**
1. **Regression prevention:** Ensures P2P changes don't break shared bridge mode
2. **Validates tc flower filters:** Confirms per-destination netem still works
3. **Heterogeneous NF:** Tests the exact scenario of different receivers on shared medium
4. **Real-world scenario:** Matches actual MANET deployments with mixed hardware

**Test must verify:**
- ✅ All-to-all directional links computed (N×(N-1) for N nodes)
- ✅ Correct receiver NF used per direction
- ✅ TC flower filters exist with correct destination IPs
- ✅ HTB hierarchy properly configured
- ✅ Different netem params per destination on single interface

### Phase 4: Documentation

**File:** `CLAUDE.md`

**Sections to update:**

1. **FAQ - "How does netem work with wireless links?"**
   - Add: "For P2P wireless links with asymmetric receiver noise figures, netem params are computed bidirectionally and applied per-interface based on egress direction."

2. **Channel Computation Pipeline**
   - Update diagram to show bidirectional computation for P2P links
   - Clarify: "For heterogeneous receivers (different NF), each direction is computed independently."

3. **Deployment Output**
   - Update example to show bidirectional link parameters

4. **Noise Figure Configuration**
   - Add: "Important: For P2P links, each direction uses its receiver's NF, resulting in asymmetric SNR and potentially different loss rates."

---

## Critical Files

### Files to Modify

| File | Purpose | Estimated LoC Change |
|------|---------|---------------------|
| [src/sine/emulation/controller.py](src/sine/emulation/controller.py) | Bidirectional channel computation | +30-50 lines |
| [tests/integration/test_noise_figure_deployment.py](tests/integration/test_noise_figure_deployment.py) | New bidirectional test | +60-80 lines |
| [CLAUDE.md](CLAUDE.md) | Documentation updates | +20-30 lines |

### Files to Review (No Changes Expected)

| File | Why No Changes |
|------|----------------|
| [src/sine/channel/server.py](src/sine/channel/server.py) | Already supports `noise_figure_db` parameter |
| [src/sine/channel/snr.py](src/sine/channel/snr.py) | Already applies NF to receiver correctly |
| [src/sine/channel/modulation.py](src/sine/channel/modulation.py) | BER/BLER formulas are SNR-based (direction-agnostic) |
| [src/sine/topology/netem.py](src/sine/topology/netem.py) | Already applies params per-interface |

---

## Verification Strategy

### Step 1: Unit Test (No Sudo)

Run new test to verify bidirectional computation logic:
```bash
uv run pytest -s tests/integration/test_noise_figure_deployment.py::test_bidirectional_asymmetric_netem
```

**Expected result:** Test passes, verifying:
- Both link states exist (forward and reverse)
- SNR difference matches NF difference (~3 dB)
- Loss rates are asymmetric (higher for worse NF)
- Delays are symmetric (same geometric path)

### Step 2: Shared Bridge Regression Test (Critical)

**MUST verify that shared bridge mode still works after P2P changes!**

Deploy `manet_triangle_shared` with asymmetric NF:

```bash
# Create modified topology with heterogeneous NF
# (Edit examples/manet_triangle_shared/network.yaml to add different noise_figure_db per node)

UV_PATH=$(which uv) sudo -E $(which uv) run sine deploy examples/manet_triangle_shared/network.yaml
```

Verify per-destination tc filters on each node:

```bash
# Get PIDs
PID1=$(docker inspect -f '{{.State.Pid}}' clab-manet-triangle-shared-node1)
PID2=$(docker inspect -f '{{.State.Pid}}' clab-manet-triangle-shared-node2)
PID3=$(docker inspect -f '{{.State.Pid}}' clab-manet-triangle-shared-node3)

# Check node1:eth1 has per-destination filters
nsenter -t $PID1 -n tc filter show dev eth1
# Should show filters for 192.168.100.2 and 192.168.100.3

# Check HTB + netem hierarchy
nsenter -t $PID1 -n tc qdisc show dev eth1
# Should show: htb root qdisc + netem on child classes

# Verify different loss rates per destination
nsenter -t $PID1 -n tc -s qdisc show dev eth1
# Should show different netem params per class (handle 10:, 20:, etc.)
```

**Expected:** Single interface (`eth1`) has multiple netem configurations via HTB classes and flower filters.

### Step 3: P2P Integration Test (Requires Sudo)

Deploy P2P asymmetric topology and verify netem configuration:

```bash
# Deploy with asymmetric NF
UV_PATH=$(which uv) sudo -E $(which uv) run sine deploy examples/vacuum_20m/network.yaml

# Inspect netem on both containers
PID1=$(docker inspect -f '{{.State.Pid}}' clab-vacuum-node1)
PID2=$(docker inspect -f '{{.State.Pid}}' clab-vacuum-node2)

nsenter -t $PID1 -n tc -s qdisc show dev eth1
nsenter -t $PID2 -n tc -s qdisc show dev eth1
```

**Expected result:** Different `loss` percentages on each interface based on receiver NF.

### Step 4: Throughput Test (Iperf3)

Verify asymmetric throughput due to different loss rates:

```bash
# Direction 1: node1 → node2 (higher loss if node2 has worse NF)
docker exec clab-vacuum-node1 iperf3 -c <node2_ip> -u -b 200M -t 10

# Direction 2: node2 → node1 (lower loss if node1 has better NF)
docker exec clab-vacuum-node2 iperf3 -c <node1_ip> -u -b 200M -t 10
```

**Expected result:** Different packet loss rates matching netem configuration.

### Step 5: Deployment Summary Check

Verify deployment summary shows both directions:

```
Link Parameters:
  node1:eth1 → node2:eth1 [wireless]
    SNR: 28.5 dB | Loss: 0.10% | Rate: 192 Mbps
  node2:eth1 → node1:eth1 [wireless]
    SNR: 31.5 dB | Loss: 0.01% | Rate: 467 Mbps
```

---

## Risk Assessment

### Low Risk Factors

- ✅ No API changes (channel server already supports NF parameter)
- ✅ No schema changes (topology YAML already supports per-interface NF)
- ✅ Pattern already exists (fixed links use identical approach)
- ✅ Existing tests unaffected (they don't validate bidirectional correctness)
- ✅ Backward compatible (no user action required)

### Potential Issues & Mitigations

| Risk | Mitigation |
|------|-----------|
| 2× channel computations increase deployment time | Acceptable for realistic emulation; optimization possible later via path loss caching |
| Link state storage doubles (two entries per link) | Negligible memory impact; typical topologies have <100 links |
| Deployment summary becomes verbose | Make it configurable or smart (detect symmetry) |
| Existing tests may expect symmetric behavior | Review and update test expectations where needed |

### Rollback Plan

If issues arise:
1. Revert controller.py changes to single-direction computation
2. Keep new test as xfail (mark as known issue)
3. Document limitation in CLAUDE.md

---

## Performance Impact

### Computational Overhead

**Current:** N×(N-1)/2 channel computations for fully-meshed topology
**Proposed:** N×(N-1) computations (2× increase)

**Example:**
- 10-node mesh: 45 → 90 computations (~4.5 seconds @ 50ms/link)
- 20-node mesh: 190 → 380 computations (~19 seconds @ 50ms/link)

**Verdict:** Acceptable for deployment-time operation. Ray tracing is already the bottleneck.

### Optimization Opportunity (Future)

Cache path loss (symmetric) and recompute only SNR with different NF:
- Ray tracing: Once per link pair (symmetric)
- SNR/BER/PER: Twice per link (asymmetric)
- **Overhead reduction: 2× → ~1.1×**

Defer until profiling shows this is necessary.

---

## Questions for User Confirmation

Before implementing, please confirm:

1. **Agree with bidirectional computation?** (Both experts strongly recommend)
2. **Deployment summary format:** Always show both directions, or detect symmetry?
3. **Optimization:** Implement path loss caching now, or defer for simplicity?
4. **Timeline:** Ready to proceed with estimated 5-9 hours of work?

---

## Implementation Checklist

- [ ] Phase 1: Modify `controller.py` for bidirectional computation in P2P mode
- [ ] Phase 2: Update deployment summary to show both directions
- [ ] Phase 3a: Add `test_bidirectional_asymmetric_netem()` for P2P mode
- [ ] Phase 3b: Add `test_shared_bridge_asymmetric_nf()` regression test (CRITICAL)
- [ ] Phase 4: Update CLAUDE.md documentation (add P2P vs shared bridge clarification)
- [ ] Verification: Run full test suite (ensure no shared bridge regressions)
- [ ] Verification: Deploy P2P asymmetric topology and inspect netem config
- [ ] Verification: Deploy `manet_triangle_shared` and verify tc flower filters
- [ ] Verification: Run iperf3 throughput tests in both directions (P2P and shared bridge)

---

---

## Expert Agent Reviews

### Wireless Communications Engineer Assessment

**Physical Model Accuracy:**
- **Shared bridge**: ✅ **Physically accurate** for WiFi 6 MANETs (matches real broadcast medium)
- **P2P model**: ⚠️ **Linux abstraction** that works but implies multi-radio system (not realistic for single-radio WiFi)

**Key Findings:**
1. **Real WiFi behavior**: Single radio interface broadcasts to all peers on shared medium
2. **Per-peer MCS**: Shared bridge's tc flower filters match real WiFi rate adaptation better than P2P's multi-interface approach
3. **Channel reciprocity**: Shared bridge naturally enforces reciprocal paths; P2P requires careful implementation
4. **Interference modeling**: Shared bridge provides true broadcast domain (hidden/exposed node problems); P2P isolates links

**Recommendation:**
- **Primary model**: Shared bridge for realistic MANET emulation
- **P2P valid for**: Multi-radio scenarios, directional links, simple testing
- **Bidirectional P2P**: Correct and necessary for asymmetric RX capabilities

**Quote:** *"For physically accurate WiFi 6 / 802.11 MANET emulation, prefer the shared bridge model. The P2P model is a functional abstraction but doesn't match real RF behavior for single-radio wireless systems."*

### Linux Networking Specialist Assessment

**Implementation Validation:**
- **Both models**: ✅ **Valid and production-ready**
- **P2P scalability**: Up to 50 nodes comfortably (20 recommended)
- **Shared bridge scalability**: Up to 100 nodes comfortably
- **Performance**: Both exceed wireless emulation requirements (10-500 Mbps typical)

**Key Findings:**

| Aspect | P2P (Multi-veth) | Shared Bridge (TC Filters) |
|--------|-----------------|---------------------------|
| **Simplicity** | ✅ Simple | ⚠️ Moderate complexity |
| **Scalability** | ⚠️ N-1 interfaces/node | ✅ Single interface |
| **Performance** | ✅ 10-40 Gbps/link | ⚠️ 5-20 Gbps/destination |
| **Broadcast** | ❌ No shared medium | ✅ True broadcast domain |
| **Real-world match** | ❌ Point-to-point WAN | ✅ WiFi/Ethernet broadcast |

**Verification Strategy:**
- Use `tc -s qdisc show`, `tc -s filter show` to inspect netem config
- Test with `iperf3` (throughput), `ping` (delay/loss)
- **Mandatory regression test** for `manet_triangle_shared` topology

**Recommendation:**
- **Choose shared bridge** for MANET scenarios (OLSR, AODV, WiFi mesh)
- **P2P acceptable** for simple 2-3 node tests or directional links
- **Bidirectional P2P**: Correct implementation, approved ✅

**Quote:** *"The proposed approach is correct and necessary for modeling asymmetric wireless links. Both models are production-ready, but shared bridge better matches broadcast WiFi behavior."*

### Consensus Recommendations

Both experts agree:
1. ✅ **Implement bidirectional P2P** as planned (correct and necessary)
2. ✅ **Shared bridge is preferred** for realistic MANET emulation
3. ✅ **Both models are valid** for different use cases
4. ✅ **Mandatory regression test** with `manet_triangle_shared/network.yaml`
5. ✅ **No blockers or concerns** from either wireless or networking perspective

---

**Prepared by:** Claude Code (Plan Mode)
**Expert Reviews:** Wireless Communications Engineer + Linux Networking Specialist
**Review Date:** 2026-01-30
**Consensus:** PROCEED with implementation
**Estimated Effort:** 5-9 hours
**Risk Level:** LOW
**Priority Additions:**
- Add regression test for shared bridge mode (critical)
- Document P2P vs shared bridge trade-offs in CLAUDE.md
- Consider adding warning when N > 50 nodes in P2P mode
