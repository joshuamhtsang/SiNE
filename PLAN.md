# WiFi 7 MLO (Multi-Link Operation) Emulation Plan for SiNE

## Executive Summary

WiFi 7 MLO enables simultaneous operation across multiple frequency bands (2.4/5/6 GHz) for increased throughput and reliability. This plan outlines how to extend SiNE to emulate MLO at the network layer using:

1. **Multi-interface per node** (eth1=5GHz, eth2=6GHz) - already supported
2. **Per-frequency ray tracing** - requires multi-scene engine architecture
3. **4096-QAM modulation** - new WiFi 7 modulation scheme
4. **Independent netem per band** - captures per-band channel conditions
5. **Linux ECMP load balancing** - emulates MAC-layer packet steering

**Expected Performance**: ~4 Gbps aggregate throughput (vs ~1.5 Gbps WiFi 6 single-link)

---

## Background: What is WiFi 7 MLO?

### Key Features

**Multi-Band Operation:**
- Simultaneous transmission across 2.4 GHz, 5 GHz, and 6 GHz bands
- Each band operates independently with its own channel access
- Different propagation characteristics per frequency

**Operating Modes:**
- **STR (Simultaneous TX/RX)**: Asynchronous, highest throughput (47% improvement)
- **EMLSR (Enhanced Multi-Link Single Radio)**: Power-efficient, single radio switches between bands
- **EMLMR (Non-STR)**: Synchronous operation, simpler implementation

**MAC Layer Architecture:**
- **UMAC (Upper MAC)**: Shared across links, handles packet steering, reordering, TID-to-link mapping
- **LMAC (Lower MAC)**: Per-link, handles channel access (CSMA/CA)

**Traffic Steering:**
- Dynamic per-packet link selection based on congestion, latency, channel quality
- TID-to-link mapping for QoS (Voice → 5 GHz, Video → 6 GHz)
- Reordering buffer ensures in-order delivery despite asynchronous links

### SiNE's Emulation Approach

**What SiNE Will Capture:**
- ✅ Multi-band propagation differences (per-frequency ray tracing)
- ✅ Independent channel quality per band (SNR, BER, PER)
- ✅ Per-link throughput and latency (netem)
- ✅ Aggregate throughput via multi-path routing
- ✅ Link failures and failover

**What SiNE Won't Capture (Acceptable Trade-offs):**
- ❌ MAC-layer packet steering (UMAC behavior) - use Linux ECMP instead
- ❌ Packet reordering at MAC layer - happens at IP layer in Linux
- ❌ Single MAC address abstraction - nodes have multiple interfaces
- ❌ Dynamic TID-to-link mapping at run-time - can be emulated with tc filters

**Rationale**: SiNE targets network emulation (Layer 3+), not PHY/MAC simulation. Application-layer sees multiple paths with accurate per-band channel conditions, achieving similar end results.

---

## Current SiNE Architecture Analysis

### Multi-Interface Support (Already Works)

SiNE supports multiple wireless interfaces per node via explicit interface-to-peer mapping:

```yaml
nodes:
  node1:
    interfaces:
      eth1:  # Link to node2
        wireless: {position: {x: 0, y: 0, z: 1}, frequency_ghz: 5.18, ...}
      eth2:  # Link to node3
        wireless: {position: {x: 0, y: 0, z: 1}, frequency_ghz: 6.43, ...}

links:
  - endpoints: [node1:eth1, node2:eth1]
  - endpoints: [node1:eth2, node3:eth1]
```

**Implementation**: `ContainerlabManager._interface_mapping` tracks `{(node, peer) → interface}` for multi-interface netem configuration.

### Key Limitations for MLO

1. **Single Scene Frequency**: Ray tracing scene is loaded once with a single frequency. Multi-band MLO requires simultaneous 5 GHz + 6 GHz ray tracing.

   ```python
   # Current (src/sine/emulation/controller.py:344)
   "scene": {
       "frequency_hz": link_requests[0]["frequency_hz"],  # Only ONE!
   }
   ```

2. **No Multi-Frequency Scene Engine**: SiNE uses one `SionnaEngine` instance per deployment, limiting all links to the same frequency.

3. **No Load Balancing**: No built-in traffic splitting across interfaces (but architecture allows ECMP integration).

---

## Implementation Plan

### Phase 1: Add 4096-QAM Support

**Goal**: Enable WiFi 7's highest modulation scheme.

**Files to Modify:**
- `src/sine/channel/modulation.py` - Add 4096-QAM BER formula
- `src/sine/config/schema.py` - Add `4096qam` to modulation enum
- `examples/wifi7_mlo/data/wifi7_5ghz_mcs.csv` - New MCS table with 4096-QAM entries
- `examples/wifi7_mlo/data/wifi7_6ghz_mcs.csv` - 320 MHz MCS table

**Changes:**

1. **Add 4096-QAM BER calculation** (`modulation.py`):
   ```python
   def compute_ber_4096qam(snr_linear: float) -> float:
       """Compute BER for 4096-QAM in AWGN channel."""
       # 4096-QAM: M=4096, k=12 bits/symbol
       # Approximate BER ≈ (63/128) * erfc(sqrt(snr_linear/341))
       return (63.0 / 128.0) * scipy.special.erfc(np.sqrt(snr_linear / 341.0))
   ```

2. **Update `compute_ber()` dispatch**:
   ```python
   modulation_ber_funcs = {
       "bpsk": compute_ber_bpsk,
       # ... existing entries
       "4096qam": compute_ber_4096qam,
   }
   ```

3. **Add to schema validation**:
   ```python
   ModulationType = Literal["bpsk", "qpsk", "16qam", "64qam", "256qam", "1024qam", "4096qam"]
   ```

4. **Create WiFi 7 MCS tables**:
   - `wifi7_5ghz_mcs.csv`: 160 MHz, MCS 0-13 (includes 4096-QAM)
   - `wifi7_6ghz_mcs.csv`: 320 MHz, MCS 0-13 (wider channels in 6 GHz band)

**Verification:**
- Unit test: BER values for 4096-QAM at various SNR levels
- Compare to WiFi 7 spec (IEEE 802.11be) sensitivity thresholds

---

### Phase 2: Multi-Frequency Scene Engine Architecture

**Goal**: Support simultaneous ray tracing at multiple frequencies.

**Files to Modify:**
- `src/sine/channel/sionna_engine.py` - Refactor to support multiple scene instances
- `src/sine/channel/server.py` - Manage per-frequency engine pool
- `src/sine/emulation/controller.py` - Request channels per-frequency

**Architecture Change:**

**Current (Single Engine)**:
```
EmulationController → ChannelServer → SionnaEngine (frequency_hz=5.18e9)
                                              ↓
                                       All links use 5.18 GHz
```

**Proposed (Multi-Engine Pool)**:
```
EmulationController → ChannelServer → EnginePool {
                                         2.4 GHz: SionnaEngine (2.4e9)
                                         5 GHz:   SionnaEngine (5.18e9)
                                         6 GHz:   SionnaEngine (6.43e9)
                                      }
                                              ↓
                                   Route links to correct engine by frequency
```

**Implementation:**

1. **Add `EnginePool` class** (`sionna_engine.py`):
   ```python
   class EnginePool:
       """Manages multiple SionnaEngine instances, one per frequency."""

       def __init__(self):
           self._engines: dict[float, SionnaEngine] = {}

       async def get_or_create_engine(self, frequency_hz: float) -> SionnaEngine:
           """Get existing engine for frequency, or create new one."""
           if frequency_hz not in self._engines:
               self._engines[frequency_hz] = SionnaEngine()
           return self._engines[frequency_hz]

       async def load_scene_for_frequency(
           self, scene_file: str, frequency_hz: float, bandwidth_hz: float
       ):
           """Load scene into frequency-specific engine."""
           engine = await self.get_or_create_engine(frequency_hz)
           await engine.load_scene(scene_file, frequency_hz, bandwidth_hz)
   ```

2. **Update `ChannelServer`** to use `EnginePool` (`server.py`):
   ```python
   class ChannelServer:
       def __init__(self):
           self._engine_pool = EnginePool()

       async def load_scene(self, request: LoadSceneRequest):
           """Load scene for specific frequency."""
           await self._engine_pool.load_scene_for_frequency(
               request.scene_file,
               request.frequency_hz,
               request.bandwidth_hz,
           )

       async def compute_single_link(self, request: ComputeSingleRequest):
           """Compute using frequency-specific engine."""
           engine = await self._engine_pool.get_or_create_engine(
               request.frequency_hz
           )
           # Use engine for computation...
   ```

3. **Update `EmulationController`** to load scenes per frequency (`controller.py`):
   ```python
   async def _load_scenes_for_frequencies(self):
       """Load scene for each unique frequency in topology."""
       frequencies = set()
       for link_req in self._build_link_requests():
           frequencies.add(link_req["frequency_hz"])

       for freq_hz in frequencies:
           logger.info(f"Loading scene for {freq_hz/1e9:.2f} GHz")
           await self.channel_client.load_scene(
               scene_file=self.config.topology.scene.file,
               frequency_hz=freq_hz,
               bandwidth_hz=link_req["bandwidth_hz"],  # Use from link
           )
   ```

**Benefits:**
- ✅ Each frequency band has accurate ray tracing (frequency-dependent material properties)
- ✅ Parallel link computation across bands
- ✅ Scalable to any number of frequencies

**Challenges:**
- ⚠️ Memory overhead: Each engine holds full scene in GPU memory (~500 MB per scene)
- ⚠️ Scene loading time: 3× overhead for 3-band MLO
- ⚠️ GPU memory limits: May need to share scenes or use CPU fallback

---

### Phase 3: MLO Example Topology

**Goal**: Create reference implementation of WiFi 7 MLO.

**New Files:**
- `examples/wifi7_mlo/network.yaml` - Dual-band (5+6 GHz) MLO topology
- `examples/wifi7_mlo/data/wifi7_5ghz_mcs.csv` - 160 MHz MCS table
- `examples/wifi7_mlo/data/wifi7_6ghz_mcs.csv` - 320 MHz MCS table
- `examples/wifi7_mlo/README.md` - MLO-specific documentation

**Topology Design:**

```yaml
name: wifi7_mlo
scene:
  file: scenes/vacuum.xml  # Empty scene for free-space propagation

nodes:
  wifi7_ap:
    kind: linux
    image: alpine:latest
    interfaces:
      eth1:  # 5 GHz link
        wireless:
          position: {x: 0, y: 0, z: 2.5}
          frequency_ghz: 5.18
          bandwidth_mhz: 160
          rf_power_dbm: 23.0
          antenna:
            pattern: dipole
            polarization: V
            gain_dbi: 3.0
          mcs_table: examples/wifi7_mlo/data/wifi7_5ghz_mcs.csv
          mcs_hysteresis_db: 2.0
          packet_size_bytes: 1500

      eth2:  # 6 GHz link
        wireless:
          position: {x: 0, y: 0, z: 2.5}  # Same position, different band
          frequency_ghz: 6.43
          bandwidth_mhz: 320  # Wider channels in 6 GHz
          rf_power_dbm: 23.0
          antenna:
            pattern: dipole
            polarization: V
            gain_dbi: 3.0
          mcs_table: examples/wifi7_mlo/data/wifi7_6ghz_mcs.csv
          mcs_hysteresis_db: 2.0
          packet_size_bytes: 1500

  client:
    kind: linux
    image: alpine:latest
    interfaces:
      eth1:  # 5 GHz link
        wireless:
          position: {x: 10, y: 0, z: 1.0}
          frequency_ghz: 5.18
          bandwidth_mhz: 160
          rf_power_dbm: 20.0
          antenna:
            pattern: dipole
            polarization: V
            gain_dbi: 2.0
          mcs_table: examples/wifi7_mlo/data/wifi7_5ghz_mcs.csv
          mcs_hysteresis_db: 2.0
          packet_size_bytes: 1500

      eth2:  # 6 GHz link
        wireless:
          position: {x: 10, y: 0, z: 1.0}
          frequency_ghz: 6.43
          bandwidth_mhz: 320
          rf_power_dbm: 20.0
          antenna:
            pattern: dipole
            polarization: V
            gain_dbi: 2.0
          mcs_table: examples/wifi7_mlo/data/wifi7_6ghz_mcs.csv
          mcs_hysteresis_db: 2.0
          packet_size_bytes: 1500

links:
  - endpoints: [wifi7_ap:eth1, client:eth1]  # 5 GHz link
  - endpoints: [wifi7_ap:eth2, client:eth2]  # 6 GHz link
```

**MCS Table Examples:**

**5 GHz (160 MHz):**
```csv
mcs_index,modulation,code_rate,min_snr_db,fec_type,bandwidth_mhz
0,bpsk,0.5,5.0,ldpc,160
1,qpsk,0.5,8.0,ldpc,160
2,qpsk,0.75,11.0,ldpc,160
3,16qam,0.5,14.0,ldpc,160
4,16qam,0.75,17.0,ldpc,160
5,64qam,0.667,20.0,ldpc,160
6,64qam,0.75,23.0,ldpc,160
7,64qam,0.833,26.0,ldpc,160
8,256qam,0.75,29.0,ldpc,160
9,256qam,0.833,32.0,ldpc,160
10,1024qam,0.75,35.0,ldpc,160
11,1024qam,0.833,38.0,ldpc,160
12,4096qam,0.75,40.0,ldpc,160
13,4096qam,0.833,43.0,ldpc,160
```

**6 GHz (320 MHz):**
```csv
mcs_index,modulation,code_rate,min_snr_db,fec_type,bandwidth_mhz
0,bpsk,0.5,5.0,ldpc,320
# ... (same modulations as 5 GHz)
12,4096qam,0.75,40.0,ldpc,320
13,4096qam,0.833,43.0,ldpc,320
```

**Expected Throughput:**
- 5 GHz (160 MHz, MCS 11): ~1.1 Gbps
- 6 GHz (320 MHz, MCS 13): ~2.9 Gbps
- **Total: ~4.0 Gbps** (STR mode assumption)

---

### Phase 4: Load Balancing Integration (Optional)

**Goal**: Emulate MLO packet steering via Linux ECMP.

**Approach**: Use Linux Equal-Cost Multi-Path (ECMP) routing to distribute traffic across both interfaces.

**Implementation:**

1. **Configure IP addresses per interface**:
   ```bash
   # On AP
   docker exec clab-wifi7-mlo-wifi7_ap ip addr add 192.168.100.1/24 dev eth1
   docker exec clab-wifi7-mlo-wifi7_ap ip addr add 192.168.100.1/24 dev eth2

   # On client
   docker exec clab-wifi7-mlo-client ip addr add 192.168.100.2/24 dev eth1
   docker exec clab-wifi7-mlo-client ip addr add 192.168.100.2/24 dev eth2
   ```

2. **Add ECMP route**:
   ```bash
   # On client (for outbound traffic)
   docker exec clab-wifi7-mlo-client ip route add default \
     nexthop via 192.168.100.1 dev eth1 weight 1 \
     nexthop via 192.168.100.1 dev eth2 weight 1
   ```

**Traffic Distribution:**
- Linux hashes flows (src/dst IP, port) to select interface
- Per-flow sticky (same flow uses same interface)
- Load balances across flows

**QoS Steering (Advanced):**

Use tc filters for TID-to-link mapping:
```bash
# Voice traffic (DSCP EF) → 5 GHz (eth1)
tc filter add dev eth0 protocol ip prio 1 u32 \
  match ip dsfield 0xb8 0xfc flowid 1:1 action mirred egress redirect dev eth1

# Video traffic (DSCP AF41) → 6 GHz (eth2)
tc filter add dev eth0 protocol ip prio 2 u32 \
  match ip dsfield 0x88 0xfc flowid 1:2 action mirred egress redirect dev eth2
```

**Limitations:**
- Not true UMAC (no reordering buffer)
- Per-flow hashing (not per-packet steering)
- No dynamic link quality feedback

**Benefits:**
- Application-layer sees aggregate throughput
- Failover works (if one link fails, traffic uses other)
- Easy to test and validate

---

### Phase 5: Documentation and Testing

**Goal**: Document MLO emulation and validate performance.

**Documentation Updates:**

1. **Add MLO section to README.md**:
   - Overview of WiFi 7 MLO
   - SiNE's emulation approach and limitations
   - Example usage and expected throughput
   - ECMP configuration guide

2. **Create `examples/wifi7_mlo/README.md`**:
   - Detailed MLO example walkthrough
   - Performance testing with iperf3
   - Per-band channel analysis
   - Troubleshooting guide

**Testing Strategy:**

1. **Unit Tests**:
   - 4096-QAM BER computation accuracy
   - Multi-frequency engine pool creation
   - Per-frequency scene loading

2. **Integration Tests**:
   - Deploy wifi7_mlo topology
   - Verify both links have independent netem configs
   - Validate different MCS selection per band (based on frequency-dependent path loss)

3. **Performance Tests**:
   ```bash
   # Deploy MLO topology
   sudo $(which uv) run sine deploy examples/wifi7_mlo/network.yaml

   # Configure IPs
   docker exec clab-wifi7-mlo-wifi7_ap ip addr add 192.168.100.1/24 dev eth1
   docker exec clab-wifi7-mlo-wifi7_ap ip addr add 192.168.100.1/24 dev eth2
   docker exec clab-wifi7-mlo-client ip addr add 192.168.100.2/24 dev eth1
   docker exec clab-wifi7-mlo-client ip addr add 192.168.100.2/24 dev eth2

   # Test per-link throughput
   docker exec clab-wifi7-mlo-wifi7_ap iperf3 -s &
   docker exec clab-wifi7-mlo-client iperf3 -c 192.168.100.1 -B 192.168.100.2 -t 30

   # Test aggregate throughput (with ECMP)
   # ... (configure ECMP routes first)
   docker exec clab-wifi7-mlo-client iperf3 -c 192.168.100.1 -P 10 -t 30
   ```

4. **Validation Criteria**:
   - ✅ 5 GHz link achieves ~1.1 Gbps (160 MHz, MCS 11)
   - ✅ 6 GHz link achieves ~2.9 Gbps (320 MHz, MCS 13)
   - ✅ Aggregate throughput ~4 Gbps with ECMP
   - ✅ Different MCS selected per band due to frequency-dependent propagation
   - ✅ Link failover works (disable one interface, traffic uses other)

---

## Critical Files Summary

| File | Purpose | Changes |
|------|---------|---------|
| `src/sine/channel/modulation.py` | BER computation | Add `compute_ber_4096qam()` |
| `src/sine/channel/sionna_engine.py` | Ray tracing engine | Add `EnginePool` class for multi-frequency |
| `src/sine/channel/server.py` | Channel server API | Use `EnginePool`, route requests by frequency |
| `src/sine/emulation/controller.py` | Deployment orchestrator | Load scenes per frequency, group links by band |
| `src/sine/config/schema.py` | Topology validation | Add `4096qam` to modulation enum |
| `examples/wifi7_mlo/network.yaml` | MLO topology | Dual-band (5+6 GHz) configuration |
| `examples/wifi7_mlo/data/wifi7_5ghz_mcs.csv` | MCS table | WiFi 7 MCS entries (160 MHz) |
| `examples/wifi7_mlo/data/wifi7_6ghz_mcs.csv` | MCS table | WiFi 7 MCS entries (320 MHz) |
| `README.md` | Main documentation | Add MLO section with usage guide |

---

## Implementation Phases Timeline

| Phase | Tasks | Complexity |
|-------|-------|------------|
| **Phase 1** | 4096-QAM support | Low (1-2 days) |
| **Phase 2** | Multi-frequency engine pool | Medium (3-5 days) |
| **Phase 3** | MLO example topology | Low (1-2 days) |
| **Phase 4** | Load balancing (optional) | Medium (2-3 days) |
| **Phase 5** | Documentation + testing | Medium (2-3 days) |

**Total Effort**: ~2-3 weeks for full implementation

---

## Verification Plan

### End-to-End Test

```bash
# 1. Start channel server
uv run sine channel-server

# 2. Deploy MLO topology (in another terminal)
sudo $(which uv) run sine deploy examples/wifi7_mlo/network.yaml

# Expected output:
# Deployment Summary:
#   wifi7_ap:eth1 ↔ client:eth1 [wireless]
#     MCS: 11 (1024qam, rate-0.833, ldpc) | Rate: 1100 Mbps | 5.18 GHz
#   wifi7_ap:eth2 ↔ client:eth2 [wireless]
#     MCS: 13 (4096qam, rate-0.833, ldpc) | Rate: 2900 Mbps | 6.43 GHz

# 3. Configure IP addressing
docker exec clab-wifi7-mlo-wifi7_ap ip addr add 192.168.100.1/24 dev eth1
docker exec clab-wifi7-mlo-wifi7_ap ip addr add 192.168.101.1/24 dev eth2
docker exec clab-wifi7-mlo-client ip addr add 192.168.100.2/24 dev eth1
docker exec clab-wifi7-mlo-client ip addr add 192.168.101.2/24 dev eth2

# 4. Test per-link throughput
docker exec clab-wifi7-mlo-wifi7_ap sh -c "iperf3 -s -p 5001 &"
docker exec clab-wifi7-mlo-wifi7_ap sh -c "iperf3 -s -p 5002 &"

docker exec clab-wifi7-mlo-client iperf3 -c 192.168.100.1 -p 5001 -t 10  # 5 GHz
docker exec clab-wifi7-mlo-client iperf3 -c 192.168.101.1 -p 5002 -t 10  # 6 GHz

# Expected: ~1.1 Gbps (5 GHz), ~2.9 Gbps (6 GHz)

# 5. Verify netem configuration
./CLAUDE_RESOURCES/check_netem.sh

# 6. Cleanup
sudo $(which uv) run sine destroy examples/wifi7_mlo/network.yaml
```

### Success Criteria

- ✅ Both 5 GHz and 6 GHz scenes load without errors
- ✅ Different MCS selected per band (frequency-dependent propagation)
- ✅ Per-link throughput matches MCS-predicted rates (±10%)
- ✅ Netem parameters applied to both eth1 and eth2
- ✅ Link parameters different per band (higher path loss at 6 GHz)
- ✅ Deployment summary shows both links with correct frequencies

---

## Future Enhancements

### 1. True Broadcast Medium (Shared Bridge Model)

Replace point-to-point veth pairs with shared bridge for all MANET nodes:

```
Current (P2P):                  Future (Shared):
Node1 ═══════ Node2             All nodes on single bridge
Node1 ═══════ Node3             with per-destination tc filters
Node2 ═══════ Node3

Pros: Simple, accurate per-link
Cons: Not a broadcast medium    Pros: True broadcast, hidden node
                                 Cons: Complex tc filter rules
```

Implementation approach:
- Create single Linux bridge
- Use eBPF/tc u32 filters for per-destination netem
- Apply worst-case channel to broadcast packets

### 2. Dynamic MCS Adaptation

Real-time MCS adjustment based on mobility/channel changes:

- Mobility API updates positions → recompute SNR → select new MCS
- Update netem params mid-flight without redeploying
- Capture link adaptation behavior

### 3. QoS-Based Traffic Steering

Implement TID-to-link mapping:

```bash
# Voice → 5 GHz (low latency)
tc filter add dev eth0 u32 match ip dsfield 0xb8 0xfc action mirred egress redirect dev eth1

# Video → 6 GHz (high bandwidth)
tc filter add dev eth0 u32 match ip dsfield 0x88 0xfc action mirred egress redirect dev eth2
```

### 4. 3-Band MLO (2.4 + 5 + 6 GHz)

Extend to full tri-band operation:

```yaml
interfaces:
  eth1: {frequency_ghz: 2.4, bandwidth_mhz: 20}   # 2.4 GHz
  eth2: {frequency_ghz: 5.18, bandwidth_mhz: 160} # 5 GHz
  eth3: {frequency_ghz: 6.43, bandwidth_mhz: 320} # 6 GHz
```

### 5. MLO Mobility Scenarios

Test MLO with moving nodes:

- AP stays static, client moves
- Channel conditions change per band (different shadowing)
- MCS adapts independently per link
- Traffic steering reacts to link quality changes

---

## Risks and Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| **GPU memory limits** (3 scenes in memory) | Cannot deploy MLO | Share scenes across engines, or use CPU fallback |
| **Scene loading overhead** (3× slower) | Slow deployment | Cache scenes per frequency, parallel loading |
| **ECMP doesn't match real MLO** | Inaccurate packet steering | Document limitations; consider tc filter rules |
| **4096-QAM BER formula inaccurate** | Wrong link capacity | Validate against WiFi 7 spec, use conservative thresholds |
| **Per-flow ECMP hashing** | Not per-packet steering | Acceptable for network emulation (application-layer sees aggregate) |

---

## Conclusion

This plan extends SiNE to emulate WiFi 7 MLO by:

1. **Adding 4096-QAM modulation** (WiFi 7's highest MCS)
2. **Multi-frequency ray tracing** via `EnginePool` architecture
3. **Dual-band topology** with independent netem per frequency
4. **Load balancing** via Linux ECMP (optional)

**Key Innovation**: SiNE's multi-interface architecture maps naturally to MLO's multi-band operation. By leveraging Sionna's frequency-dependent ray tracing and applying independent netem per band, we achieve accurate network-layer emulation of MLO without requiring full MAC-layer simulation.

**Expected Outcome**: ~4 Gbps aggregate throughput, accurate per-band channel conditions, and application-layer visibility into multi-path behavior.

---

# True Broadcast Medium (Shared Bridge Model) Implementation Plan

## Overview

Migrate SiNE's MANET emulation from **point-to-point veth pairs** to a **shared broadcast domain** using a Linux bridge with per-destination netem filtering. This enables realistic MANET behavior including broadcast medium, hidden node problems, and single-interface-per-node architecture.

**Status**: Design phase complete, awaiting implementation credits

## Key Decisions

1. **Coexistence Model**: Both point-to-point and shared bridge modes will coexist
   - Shared bridge is **opt-in** via `shared_bridge.enabled: true` in YAML
   - Existing topologies continue using P2P model (backward compatible)
   - Users can choose which model fits their use case

2. **TC Filter Technology**: **flower filters** for Phase 1 (MVP)
   - Hash-based O(1) lookup (better than u32's O(N) linear search)
   - Supports 30+ nodes efficiently (vs. u32's 10-node practical limit)
   - Minimal complexity overhead, **requires kernel 4.2+** (standard on modern systems)
   - Future: eBPF for extreme scale (1000+ nodes)

3. **IP Address Assignment**: **User-specified in YAML**
   - Each interface gets explicit `ip_address` field
   - Schema validates uniqueness at load time
   - More flexible than auto-assignment, prevents hidden magic
   - Clear error messages for IP conflicts

4. **Link Types**: **Wireless-only for Phase 1**
   - Shared bridge only supports wireless interfaces (simpler implementation)
   - Mixed wireless + fixed_netem nodes not supported initially
   - Wired links continue using separate P2P model
   - Future: Support mixed mode after wireless-only is proven

## Architecture Comparison

### Current (Point-to-Point)
```
Node1:eth1 ═══════ Node2:eth1    3 nodes = 3 veth pairs
Node1:eth2 ═══════ Node3:eth1    Each node has N-1 interfaces
Node2:eth2 ═══════ Node3:eth2    Simple netem (one per interface)
```

**Pros:** Simple, accurate per-link conditions
**Cons:** Not broadcast, no hidden node, multiple interfaces per node

### Proposed (Shared Bridge)
```
         Linux Bridge (br0)
              ├── Node1:eth1 (HTB + per-dest filters)
              ├── Node2:eth1 (HTB + per-dest filters)
              └── Node3:eth1 (HTB + per-dest filters)
```

**Pros:** True broadcast, hidden node modeling, single interface
**Cons:** Complex tc filter rules, requires HTB hierarchy

## Technical Approach

### Per-Destination Netem Architecture

Each node interface requires a 3-layer TC hierarchy:

```
Root HTB qdisc
  └── Parent class (1:1, unlimited)
       ├── Class 1:10 → Netem (to Node2) → Filter (dst 192.168.100.2)
       ├── Class 1:20 → Netem (to Node3) → Filter (dst 192.168.100.3)
       └── Class 1:99 → Netem (broadcast)  → Default (no filter)
```

**Example commands (using flower filters):**
```bash
# HTB root + parent class
tc qdisc add dev eth1 root handle 1: htb default 99
tc class add dev eth1 parent 1: classid 1:1 htb rate 1000mbit

# Default class for broadcast/multicast (MANET routing)
tc class add dev eth1 parent 1:1 classid 1:99 htb rate 1000mbit
tc qdisc add dev eth1 parent 1:99 handle 99: netem delay 1ms

# Per-destination class + netem + flower filter (hash-based)
tc class add dev eth1 parent 1:1 classid 1:10 htb rate 200mbit
tc qdisc add dev eth1 parent 1:10 handle 10: netem delay 10ms 1ms loss 0.1%
tc filter add dev eth1 protocol ip parent 1:0 prio 1 \
    flower dst_ip 192.168.100.2 action pass flowid 1:10
```

**Why flower instead of u32:**
- **O(1) hash lookup** vs. O(N) linear search
- Supports **1000+ destinations** efficiently
- **Same syntax complexity** as u32
- **Better performance** at scale (< 2 μs per packet)

## Implementation Phases

### Phase 1: Schema and YAML Changes
- Add `SharedBridgeDomain` model to `src/sine/config/schema.py`
- Add `ip_address` field to `InterfaceConfig`
- Validation: mutual exclusion of `shared_bridge` and `links`
- Validation: IP uniqueness, wireless-only enforcement

### Phase 2: Containerlab Integration
- Add `generate_shared_bridge_topology()` to `ContainerlabManager`
- Bridge topology generation with `kind: bridge` nodes
- Update `deploy()` to detect and route to bridge mode

### Phase 3: Per-Destination Netem Implementation
- **New file**: `src/sine/topology/shared_netem.py`
- `SharedNetemConfigurator` class for HTB + flower filter setup
- `apply_bridge_ips()` to configure user-specified IPs
- TC command generation and execution via `nsenter`

### Phase 4: Channel Computation for Shared Bridge
- Add `_update_shared_bridge_links()` to `EmulationController`
- All-to-all link computation (N×(N-1) links for N nodes)
- Build per-node destination maps
- Apply per-destination netem to all bridge interfaces

### Phase 5: Testing and Validation
- Create `examples/manet_triangle_shared/` example
- TC configuration verification tests
- Ping RTT validation (2× one-way delay)
- Filter match statistics verification
- MANET routing protocol testing (OLSR, BATMAN-adv)

### Phase 6: Deployment Summary and Documentation
- Update deployment summary for shared bridge mode
- Show per-node, per-destination link parameters
- Update README.md with shared bridge documentation
- Add troubleshooting guide for TC filters

## Example YAML (Shared Bridge)

```yaml
topology:
  name: manet-triangle-shared
  scene:
    file: scenes/vacuum.xml
  shared_bridge:
    enabled: true
    name: manet-br0
    nodes: [node1, node2, node3]
    interface_name: eth1  # Single interface per node

nodes:
  node1:
    kind: linux
    image: alpine:latest
    interfaces:
      eth1:
        ip_address: 192.168.100.1  # User-specified IP for tc filters
        wireless:
          position: {x: 0, y: 0, z: 1}
          frequency_ghz: 5.18
          rf_power_dbm: 20.0
          # ... other wireless params
  node2:
    kind: linux
    image: alpine:latest
    interfaces:
      eth1:
        ip_address: 192.168.100.2
        wireless: {position: {x: 10, y: 0, z: 1}, ...}
  node3:
    kind: linux
    image: alpine:latest
    interfaces:
      eth1:
        ip_address: 192.168.100.3
        wireless: {position: {x: 5, y: 8.66, z: 1}, ...}
```

## Critical Files to Modify

| File | Changes | Lines Est. |
|------|---------|-----------|
| `src/sine/config/schema.py` | Add `SharedBridgeDomain`, validators | +100 |
| `src/sine/topology/manager.py` | Add `generate_shared_bridge_topology()`, `apply_bridge_ips()` | +80 |
| `src/sine/topology/shared_netem.py` | **NEW FILE** - `SharedNetemConfigurator` | +150 |
| `src/sine/emulation/controller.py` | Add `_update_shared_bridge_links()`, update deploy logic | +120 |
| `examples/manet_triangle_shared/network.yaml` | **NEW FILE** - Example shared bridge topology | +60 |

**Total:** ~510 lines of new code

## Performance Characteristics

| Scenario | Filter Type | Nodes | CPU Overhead | Recommendation |
|----------|-------------|-------|--------------|----------------|
| Small MANET | flower | 3-10 | < 2% | ✅ Phase 1 MVP |
| Medium MANET | flower | 10-30 | < 3% | ✅ Phase 1 MVP |
| Large MANET | eBPF | 30+ | < 1% | Future phase |

- **Latency overhead**: < 30 μs (filter lookup + bridge forwarding)
- **Scalability**: flower filters support 30+ nodes efficiently (O(1) hash lookup)
- **Future**: eBPF classifiers for 100+ node deployments

## Success Metrics

- ✅ 3-node MANET deploys successfully
- ✅ Ping RTT matches expected values (within 10%)
- ✅ OLSR routing protocol converges
- ✅ Broadcast traffic uses default class
- ✅ CPU overhead < 5% for 10-node MANET
- ✅ Throughput matches configured rate limits

## References

- **Full plan**: `/home/joshua/.claude/plans/bright-crunching-fairy.md`
- **TC Guide**: `/tmp/per_destination_netem_guide.md` (comprehensive 500+ line reference)
- **Test Script**: `/tmp/test_per_dest_netem.sh` (executable demo)
- **Research Agents**:
  - `ae3dd51` (MANET implementation exploration)
  - `ac00d9c` (TC filter research)
