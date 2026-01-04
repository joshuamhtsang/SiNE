# Real-Time Scene Viewer Implementation Plan

## Overview

Implement a real-time visualization system that displays the running SiNE emulation with live node positions, ray-traced propagation paths, and channel quality metrics in a Jupyter notebook.

## Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                    Jupyter Notebook (viewer_live.ipynb)          │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │  • HTTP polling loop (configurable interval, default 1s)   │ │
│  │  • Query mobility API (port 8001) for node positions       │ │
│  │  • Query channel server (port 8000) for ray paths          │ │
│  │  • Render scene with Sionna preview widget                 │ │
│  │  • Display metrics (SNR, throughput, modulation) in UI     │ │
│  └─────────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────────┘
          ↓ HTTP GET/POST                    ↓ HTTP POST
┌─────────────────────────┐    ┌──────────────────────────────────┐
│ Mobility API (8001)     │    │ Channel Server (8000)            │
│ [EXTEND]                │    │ [EXTEND]                         │
├─────────────────────────┤    ├──────────────────────────────────┤
│ GET /api/emulation/state│    │ GET /api/scene/geometry          │
│   ├─ Scene file path    │    │   ├─ Scene file path             │
│   ├─ All node positions │    │   ├─ Object list (name, material,│
│   ├─ Link states        │    │   │   center, bbox)              │
│   ├─ MCS info           │    │   └─ Scene dimensions            │
│   └─ Emulation status   │    │                                  │
│                         │    │ POST /api/paths/all              │
│ [EXISTING]              │    │   ├─ Input: list of (tx, rx)     │
│ GET /api/nodes          │    │   │   positions                  │
│   └─ All node positions │    │   └─ Output: paths for each pair │
│                         │    │                                  │
│                         │    │ [EXISTING]                       │
│                         │    │ POST /debug/paths                │
│                         │    │   └─ Single TX/RX pair paths     │
└─────────────────────────┘    └──────────────────────────────────┘
          ↓                              ↓
┌─────────────────────────┐    ┌──────────────────────────────────┐
│ EmulationController     │    │ SionnaEngine                     │
│ - config.topology       │    │ - scene (Sionna Scene object)    │
│ - _link_states          │    │ - path_solver                    │
│ - _link_mcs_info        │    │ - _transmitters, _receivers      │
└─────────────────────────┘    └──────────────────────────────────┘
```

## Implementation Tasks

### Phase 1: Extend Mobility API (Port 8001) - OPTIONAL

**File**: `src/sine/mobility/api.py`

**Optional Endpoint**: `GET /api/emulation/metrics`

Returns link metrics (SNR, throughput, modulation) for display alongside visualization.

**Note**: This is OPTIONAL - the channel server's `/api/visualization/state` already provides device positions and paths. The mobility API could optionally provide netem metrics for a complete picture.

```python
@app.get("/api/emulation/metrics")
async def get_emulation_metrics():
    """Get link metrics (SNR, rate, modulation) for visualization overlays."""
    if not self.controller:
        raise HTTPException(503, "Emulation not running")

    links = []
    for link in self.controller.config.topology.links:
        tx_node, tx_iface = link.endpoints[0].split(":")
        rx_node, rx_iface = link.endpoints[1].split(":")

        link_key = (f"{tx_node}:{tx_iface}", f"{rx_node}:{rx_iface}")
        netem_params = self.controller._link_states.get(link_key)
        mcs_info = self.controller._link_mcs_info.get(link_key, {})

        if netem_params:  # Only wireless links
            links.append({
                "tx": f"{tx_node}:{tx_iface}",
                "rx": f"{rx_node}:{rx_iface}",
                "rate_mbps": netem_params.rate_mbps,
                "loss_percent": netem_params.loss_percent,
                "delay_ms": netem_params.delay_ms,
                "snr_db": mcs_info.get("snr_db"),
                "modulation": mcs_info.get("modulation"),
                "mcs_index": mcs_info.get("mcs_index")
            })

    return {"links": links}
```

**Decision**: This endpoint is optional. We can start without it and add later if needed for displaying metrics in the visualization.

---

### Phase 2: Extend Channel Server (Port 8000) - CACHING ARCHITECTURE

**File**: `src/sine/channel/server.py`

#### Step 1: Add Global Path Cache

Store computed paths in memory when channels are computed:

```python
# Add to global state (top of server.py)
_path_cache: dict[str, dict] = {}  # {link_id: {tx_pos, rx_pos, path_details}}
_device_positions: dict[str, tuple[float, float, float]] = {}  # {device_name: (x,y,z)}
```

#### Step 2: Modify `/compute/single` to Cache Paths

Update the existing `/compute/single` endpoint to store path details **with enhanced wireless channel metrics**:

```python
def calculate_k_factor(path_details: PathDetails) -> float | None:
    """Calculate Rician K-factor (LOS/NLOS power ratio).

    K = P_LOS / P_NLOS
    K_dB = 10×log10(K)

    Returns None if no LOS path exists.
    """
    los_paths = [p for p in path_details.paths if p.is_los]
    nlos_paths = [p for p in path_details.paths if not p.is_los]

    if not los_paths:
        return None

    # Convert dB to linear power
    p_los = 10 ** (los_paths[0].power_db / 10)
    p_nlos_total = sum(10 ** (p.power_db / 10) for p in nlos_paths)

    if p_nlos_total < 1e-20:
        return 100.0  # Very strong LOS, weak multipath

    k_linear = p_los / p_nlos_total
    k_db = 10 * np.log10(k_linear)

    return float(k_db)

@app.post("/compute/single", response_model=ChannelResponse)
async def compute_single_channel(request: WirelessLinkRequest) -> ChannelResponse:
    global _engine, _mcs_tables, _path_cache, _device_positions

    # ... [existing computation code] ...

    # Compute paths
    path_result = _engine.compute_paths()

    # NEW: Before clear_devices(), cache the path details with wireless metrics
    try:
        path_details = _engine.get_path_details()

        # Store in cache with link identifier
        link_id = f"{request.tx_node}:{request.tx_iface}->{request.rx_node}:{request.rx_iface}"

        # Calculate Rician K-factor (LOS/NLOS characterization)
        k_factor_db = calculate_k_factor(path_details)

        # Calculate coherence bandwidth from RMS delay spread
        # Bc ≈ 1/(5×τ_rms) - indicates frequency selectivity
        if path_result.delay_spread_ns > 0:
            coherence_bw_hz = 1.0 / (5.0 * path_result.delay_spread_ns * 1e-9)
        else:
            coherence_bw_hz = request.bandwidth_hz  # No multipath, flat channel

        # Limit to 5 strongest paths for visualization
        sorted_paths = sorted(path_details.paths, key=lambda p: p.power_db, reverse=True)
        limited_paths = sorted_paths[:5]

        # Calculate power coverage of shown paths
        total_power_linear = sum(10**(p.power_db/10) for p in path_details.paths)
        shown_power_linear = sum(10**(p.power_db/10) for p in limited_paths)
        power_coverage_pct = 100 * shown_power_linear / total_power_linear if total_power_linear > 0 else 0

        # Convert to JSON-serializable format
        paths_data = [{
            "delay_ns": float(p.delay_ns),
            "power_db": float(p.power_db),
            "vertices": [[float(v[0]), float(v[1]), float(v[2])] for v in p.vertices],
            "interaction_types": p.interaction_types,
            "is_los": p.is_los,
            "doppler_hz": float(p.doppler_hz) if hasattr(p, 'doppler_hz') and p.doppler_hz is not None else None,
        } for p in limited_paths]

        _path_cache[link_id] = {
            "tx_name": f"{request.tx_node}:{request.tx_iface}",
            "rx_name": f"{request.rx_node}:{request.rx_iface}",
            "tx_position": [tx_pos[0], tx_pos[1], tx_pos[2]],
            "rx_position": [rx_pos[0], rx_pos[1], rx_pos[2]],
            "distance_m": float(path_details.distance_m),
            "num_paths_total": path_details.num_paths,
            "num_paths_shown": len(paths_data),
            "power_coverage_percent": float(power_coverage_pct),

            # NEW: Wireless channel metrics
            "rms_delay_spread_ns": float(path_result.delay_spread_ns),
            "coherence_bandwidth_hz": float(coherence_bw_hz),
            "k_factor_db": float(k_factor_db) if k_factor_db is not None else None,
            "dominant_path_type": path_result.dominant_path_type,

            "paths": paths_data
        }

        # Also store device positions
        _device_positions[f"{request.tx_node}:{request.tx_iface}"] = tx_pos
        _device_positions[f"{request.rx_node}:{request.rx_iface}"] = rx_pos

    except Exception as e:
        logger.warning(f"Failed to cache paths for visualization: {e}")

    # ... [rest of existing code] ...
    return ChannelResponse(...)  # Existing return
```

**Key Additions (Wireless Metrics):**
- **RMS Delay Spread** (τ_rms): Indicates severity of inter-symbol interference (ISI)
- **Coherence Bandwidth** (Bc ≈ 1/(5×τ_rms)): Determines if channel is frequency-selective
- **Rician K-factor**: LOS/NLOS power ratio - characterizes channel type
- **Power Coverage**: Percentage of total channel power captured by shown paths
- **Doppler Shifts**: Per-path Doppler (for mobility scenarios)

#### Step 3: New Endpoint - `GET /api/visualization/state`

Single endpoint that returns everything needed for visualization:

```python
@app.get("/api/visualization/state")
async def get_visualization_state() -> dict:
    """Get complete visualization state (scene, devices, paths).

    Returns cached data from previous channel computations.
    No ray tracing is performed - this is instant.
    """
    global _engine, _path_cache, _device_positions

    if not _engine or not _engine._scene_loaded:
        raise HTTPException(404, "No scene loaded")

    # Extract scene geometry
    scene_objects = []
    for name, obj in _engine.scene.objects.items():
        pos = obj.position
        bbox = obj.mi_mesh.bbox()
        scene_objects.append({
            "name": name,
            "material": obj.radio_material.name,
            "center": [float(pos[0][0]), float(pos[1][0]), float(pos[2][0])],
            "bbox_min": [float(bbox.min[0]), float(bbox.min[1]), float(bbox.min[2])],
            "bbox_max": [float(bbox.max[0]), float(bbox.max[1]), float(bbox.max[2])]
        })

    # Convert device positions to simple dict
    devices = [{
        "name": name,
        "position": {"x": pos[0], "y": pos[1], "z": pos[2]}
    } for name, pos in _device_positions.items()]

    # Return cached paths (already JSON-serializable)
    paths = list(_path_cache.values())

    return {
        "scene_file": str(_engine.scene_path) if hasattr(_engine, 'scene_path') else None,
        "scene_loaded": True,
        "scene_objects": scene_objects,
        "devices": devices,
        "paths": paths,
        "cache_size": len(_path_cache)
    }
```

```python
# GET /api/visualization/state Response (ENHANCED):
{
  "scene_file": str,                # Path to Mitsuba XML
  "scene_loaded": bool,
  "scene_objects": [               # Scene geometry
    {
      "name": str,
      "material": str,
      "center": [x, y, z],
      "bbox_min": [x, y, z],
      "bbox_max": [x, y, z]
    }
  ],
  "devices": [                     # Current device positions
    {
      "name": str,                 # e.g., "node1:eth1"
      "position": {"x": float, "y": float, "z": float}
    }
  ],
  "paths": [                       # Cached paths from previous computations
    {
      "tx_name": str,
      "rx_name": str,
      "tx_position": [x, y, z],
      "rx_position": [x, y, z],
      "distance_m": float,
      "num_paths_total": int,
      "num_paths_shown": int,      # Limited to 5 strongest
      "power_coverage_percent": float,  # NEW: % of total power in shown paths

      # NEW: Wireless channel metrics
      "rms_delay_spread_ns": float,     # RMS delay spread (ISI indicator)
      "coherence_bandwidth_hz": float,  # Bc ≈ 1/(5×τ_rms)
      "k_factor_db": float | null,      # Rician K-factor (LOS/NLOS ratio)
      "dominant_path_type": str,        # "los", "nlos", "diffraction"

      "paths": [
        {
          "delay_ns": float,
          "power_db": float,
          "vertices": [[x, y, z], ...],
          "interaction_types": [str],
          "is_los": bool,
          "doppler_hz": float | null    # NEW: Per-path Doppler shift
        }
      ]
    }
  ],
  "cache_size": int                # Number of links in cache
}
```

**Note**: Add to `src/sine/channel/sionna_engine.py` if needed:
```python
# Store scene path for later reference
def load_scene(self, scene_path=None, ...):
    # ... existing code ...
    self.scene_path = Path(scene_path) if scene_path else None
```

---

### Phase 3: Create Live Viewer Notebook

**File**: `scenes/viewer_live.ipynb`

**Cell 1: Setup and Configuration**
```python
import asyncio
import httpx
from IPython.display import clear_output, display
from sionna.rt import load_scene, Transmitter, Receiver, PlanarArray

# Configuration
MOBILITY_API = "http://localhost:8001"
CHANNEL_API = "http://localhost:8000"
UPDATE_INTERVAL_SEC = 1.0  # Poll interval
MAX_RENDER_PATHS = 5       # Limit paths per link for performance
```

**Cell 2: Helper Functions**
```python
async def fetch_visualization_state():
    """Fetch complete visualization state from channel server.

    Returns scene geometry, device positions, and CACHED paths.
    No computation required - instant response.
    """
    async with httpx.AsyncClient(timeout=5.0) as client:
        response = await client.get(f"{CHANNEL_API}/api/visualization/state")
        response.raise_for_status()
        return response.json()

async def fetch_metrics():
    """Optionally fetch link metrics (SNR, rate, modulation) from mobility API."""
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            response = await client.get(f"{MOBILITY_API}/api/emulation/metrics")
            response.raise_for_status()
            return response.json()
    except Exception:
        return None  # Metrics are optional
```

**Cell 3: Rendering Functions (ENHANCED with Wireless Metrics)**
```python
def display_visualization(viz_state, metrics=None):
    """Display visualization state with wireless channel analysis."""
    print(f"=== Visualization State (Cache: {viz_state['cache_size']} links) ===\n")

    # Display device positions
    print("Devices:")
    for device in viz_state["devices"]:
        pos = device["position"]
        print(f"  {device['name']}: ({pos['x']:.1f}, {pos['y']:.1f}, {pos['z']:.1f})")

    # Display detailed channel information
    print(f"\n{'='*70}")
    print("WIRELESS CHANNEL ANALYSIS")
    print(f"{'='*70}")

    for link_data in viz_state["paths"]:
        print(f"\nLink: {link_data['tx_name']} → {link_data['rx_name']}")
        print(f"{'-'*70}")

        # Basic link info
        print(f"Distance: {link_data['distance_m']:.1f} m")
        print(f"Paths: {link_data['num_paths_shown']}/{link_data['num_paths_total']} "
              f"({link_data.get('power_coverage_percent', 100):.1f}% power)")

        # Delay spread analysis (ISI characterization)
        rms_ds_ns = link_data.get('rms_delay_spread_ns', 0)
        bc_mhz = link_data.get('coherence_bandwidth_hz', 0) / 1e6

        print(f"\nDelay Characteristics:")
        print(f"  RMS Delay Spread (τ_rms): {rms_ds_ns:.2f} ns")
        print(f"  Coherence Bandwidth (Bc): {bc_mhz:.1f} MHz")

        # Frequency selectivity assessment
        # Assume 80 MHz signal BW (adjust based on your config)
        signal_bw_mhz = 80  # TODO: Get from link config
        if bc_mhz > signal_bw_mhz:
            print(f"  ✓ Frequency-flat channel (Bc > BW)")
        else:
            print(f"  ⚠ Frequency-selective channel (Bc ≈ BW)")
            print(f"    ISI may be significant - OFDM recommended")

        # LOS/NLOS classification via Rician K-factor
        k_factor = link_data.get('k_factor_db')
        dominant_type = link_data.get('dominant_path_type', 'unknown')

        print(f"\nChannel Classification:")
        if k_factor is not None:
            print(f"  Rician K-factor: {k_factor:.1f} dB")
            if k_factor > 10:
                print(f"  → Strong LOS component (K > 10 dB)")
            elif k_factor > 0:
                print(f"  → Moderate LOS with multipath (0 < K < 10 dB)")
            else:
                print(f"  → NLOS dominant (K < 0 dB)")
        else:
            print(f"  Channel Type: NLOS (no direct path)")
            print(f"  Dominant: {dominant_type}")

        # Individual path details
        print(f"\nPropagation Paths (strongest {link_data['num_paths_shown']}):")
        for i, path in enumerate(link_data['paths'], 1):
            los_marker = " [LOS]" if path['is_los'] else ""
            interactions = ", ".join(path['interaction_types']) if path['interaction_types'] else "direct"
            doppler = f", Doppler: {path.get('doppler_hz', 0):.1f} Hz" if path.get('doppler_hz') is not None else ""

            print(f"  Path {i}: {path['delay_ns']:.2f} ns, {path['power_db']:.1f} dB{los_marker}")
            print(f"          Interactions: {interactions}{doppler}")

    # Display optional netem metrics
    if metrics:
        print(f"\n{'='*70}")
        print("NETEM CONFIGURATION")
        print(f"{'='*70}")
        for link in metrics.get("links", []):
            print(f"\n{link['tx']} ↔ {link['rx']}")
            print(f"  Rate: {link['rate_mbps']:.1f} Mbps")
            print(f"  Loss: {link['loss_percent']:.2f}%")
            print(f"  Delay: {link.get('delay_ms', 'N/A')} ms")
            print(f"  SNR: {link.get('snr_db', 'N/A')} dB")
            if link.get('modulation'):
                mcs_idx = link.get('mcs_index', 'N/A')
                print(f"  Modulation: {link['modulation']} (MCS {mcs_idx})")
```

**Cell 4: Main Visualization Loop**
```python
async def visualization_loop():
    """Main loop for real-time visualization.

    Polls channel server every second for cached visualization state.
    No computation performed in notebook - instant updates.
    """
    iteration = 0
    while True:
        try:
            clear_output(wait=True)
            print(f"=== Real-Time Visualization (Iteration {iteration}) ===\n")

            # Fetch cached visualization state (instant - no computation)
            viz_state = await fetch_visualization_state()

            # Optionally fetch metrics from mobility API
            metrics = await fetch_metrics()

            # Display state
            display_visualization(viz_state, metrics)

            iteration += 1
            await asyncio.sleep(UPDATE_INTERVAL_SEC)

        except KeyboardInterrupt:
            print("\nVisualization stopped.")
            break
        except Exception as e:
            print(f"Error: {e}")
            await asyncio.sleep(UPDATE_INTERVAL_SEC)

# Run the loop
await visualization_loop()
```

**Cell 5: One-Time Snapshot (Alternative to Loop)**
```python
async def render_snapshot():
    """Render a single snapshot of current visualization state."""
    # Fetch current state
    viz_state = await fetch_visualization_state()
    metrics = await fetch_metrics()

    # Display
    display_visualization(viz_state, metrics)

# Run snapshot
await render_snapshot()
```

**Cell 6: Sionna Scene Preview (Future Enhancement)**
```python
# TODO: Add Sionna scene.preview() rendering with paths
# This would require:
# 1. Load scene from viz_state["scene_file"]
# 2. Add devices from viz_state["devices"]
# 3. Convert viz_state["paths"] to Sionna paths format
# 4. Call scene.preview(paths=..., clip_at=3.0)
#
# For now, we're just displaying text output.
# Scene rendering can be added as Phase 4 after basic visualization works.
```

---

## Critical Files to Modify

1. **`src/sine/channel/server.py`** (MAIN - Caching & new endpoint with wireless metrics)
   - Add global variables: `_path_cache`, `_device_positions`
   - Add `calculate_k_factor()` helper function for Rician K-factor calculation
   - Modify `/compute/single` to cache paths with enhanced wireless metrics:
     - RMS delay spread (τ_rms)
     - Coherence bandwidth (Bc ≈ 1/(5×τ_rms))
     - Rician K-factor (LOS/NLOS power ratio)
     - Power coverage percentage
     - Per-path Doppler shifts (if available)
   - Add new endpoint: `GET /api/visualization/state`

2. **`src/sine/channel/sionna_engine.py`** (Minor enhancements)
   - Store `self.scene_path` in `load_scene()` method for later reference
   - (Phase 2) Extract Doppler information from `paths.doppler` property
   - (Phase 2) Add `doppler_hz` field to `SinglePathInfo` dataclass

3. **`src/sine/mobility/api.py`** (OPTIONAL - metrics endpoint)
   - Optionally add `GET /api/emulation/metrics` endpoint

4. **`scenes/viewer_live.ipynb`** (New file with wireless channel analysis)
   - Jupyter notebook that polls `/api/visualization/state`
   - Enhanced display with wireless channel metrics:
     - Delay spread and coherence bandwidth analysis
     - Frequency selectivity assessment (flat vs selective)
     - LOS/NLOS classification via K-factor
     - Per-path details with interaction types and Doppler
     - Netem configuration overlay
   - No computation in notebook - all data from cache

---

## Testing Strategy

### Unit Tests
- Test new API endpoints with mock data
- Verify JSON serialization of Mitsuba/DrJit types

### Integration Tests
1. Deploy `examples/two_rooms/` emulation with mobility
2. Run `viewer_live.ipynb` and verify:
   - Emulation state fetched correctly
   - Scene geometry loaded
   - Paths rendered for all links
3. Move node2 with mobility script, verify positions update in viewer

### Performance Considerations
- Path computation is expensive (~100-500ms per link)
- Limit rendering to subset of paths (strongest N paths)
- Consider caching paths if positions haven't changed
- For many nodes, use longer update intervals (2-5 seconds)

---

## Future Enhancements (Out of Scope)

1. **WebSocket Support**: Replace HTTP polling with push notifications
2. **3D Path Visualization**: Use Plotly/Three.js for interactive 3D rays
3. **Historical Data**: Track SNR/throughput over time, plot trends
4. **Coverage Heatmaps**: Grid-based SNR queries for 2D heatmap
5. **Real-Time Metrics Dashboard**: Grafana/Prometheus integration

---

## User Requirements (Confirmed)

Based on user feedback:

1. **Update interval**: **1 second** - Good balance between responsiveness and server load
2. **Path computation**: **Channel server computes paths via FastAPI** - Jupyter notebook only fetches and visualizes pre-computed paths
3. **Multi-link visualization**: **Show strongest 5 paths per link** - Cleaner visualization, faster rendering
4. **Interface**: **Jupyter notebook only** - Simplest implementation, integrates with existing viewer.ipynb

## Key Architecture Decision (REVISED)

**Critical Insight from User**: The channel server **already computes** paths when the emulation controller requests channel computation (to set netem parameters). We should **cache these paths** in the channel server's memory and return them when the viewer queries for visualization data.

**Revised Architecture**:
1. **During emulation deployment/mobility updates**: Channel server computes paths for netem → stores paths in memory cache
2. **When viewer queries**: Channel server returns cached paths + node positions (no recomputation!)
3. **Jupyter notebook**: Simply visualizes the cached data

**Benefits**:
- Zero redundant ray tracing computation
- Instant response for visualization queries
- Paths are always in sync with current netem parameters
- Simpler notebook code (single endpoint call)

**Trade-off**: Channel server memory usage increases slightly (storing path vertices for all links)

---

## Wireless Communications Engineering Review

### Overview

The plan was reviewed by a wireless communications specialist with expertise in Nvidia Sionna, channel estimation, MIMO systems, and O-RAN frameworks. The review identified several opportunities to enhance the visualization with critical wireless channel metrics that Sionna already computes during ray tracing.

### Key Findings

**✅ Strengths:**
- Caching architecture is sound - zero redundant ray tracing
- Efficient memory usage with 5-path limit
- Instant visualization queries via cached data

**⚠️ Enhancements Needed:**
- Critical wireless metrics are computed but not exposed to visualization
- Missing delay spread, coherence bandwidth, and K-factor calculations
- No Doppler information cached (important for mobility scenarios)
- Update interval may be too slow for high-mobility scenarios

### Enhanced Wireless Metrics (Added to Plan)

The following metrics have been integrated into Phase 2:

| Metric | Formula | Purpose | Impact |
|--------|---------|---------|--------|
| **RMS Delay Spread** | τ_rms (from Sionna CIR) | Indicates ISI severity | **Critical** for debugging |
| **Coherence Bandwidth** | Bc ≈ 1/(5×τ_rms) | Frequency selectivity | **High** - determines if OFDM needed |
| **Rician K-factor** | K = P_LOS / P_NLOS | LOS/NLOS characterization | **Medium** - channel type |
| **Power Coverage** | % of total power in shown paths | Validation metric | **Low** - confidence indicator |
| **Doppler Shifts** | Per-path from Sionna | Channel dynamics | **High** for mobility |

### Wireless Theory Context

**Delay Spread and ISI:**
```
If τ_rms > symbol_period → Inter-Symbol Interference (ISI)
Example: τ_rms = 50 ns, symbol_rate = 20 MHz (50 ns period) → Severe ISI
Solution: OFDM (splits into narrowband subcarriers)
```

**Coherence Bandwidth:**
```
Bc ≈ 1/(5×τ_rms)
If Bc >> signal_BW → Frequency-flat channel (simple equalization)
If Bc ≈ signal_BW → Frequency-selective (OFDM recommended)

Example: τ_rms = 50 ns → Bc = 4 MHz
        If signal_BW = 80 MHz → Frequency-selective channel
```

**Rician K-factor:**
```
K_dB = 10·log10(P_LOS / P_NLOS)
K > 10 dB → Strong LOS (low fading variance)
0 < K < 10 dB → Mixed LOS + multipath
K < 0 dB → NLOS dominant (Rayleigh-like fading)
```

**Coherence Time (for mobility):**
```
Tc ≈ 9 / (16π × fd_max)
where fd = v × fc / c (Doppler spread)

Example: v = 1 m/s, fc = 5.18 GHz
→ fd = 17.3 Hz
→ Tc = 10.3 ms
→ Recommended update interval: ~5-10 ms (5-10× Nyquist)

Current 1-second interval is adequate for pedestrian but too slow for vehicular.
```

### Implementation Priority

**Phase 1 - Critical (Included in Current Plan):**
1. ✅ Cache RMS delay spread from `path_result.delay_spread_ns`
2. ✅ Calculate coherence bandwidth: `Bc = 1/(5×τ_rms)`
3. ✅ Calculate Rician K-factor via `calculate_k_factor()` function
4. ✅ Add power coverage percentage
5. ✅ Enhanced notebook display with channel analysis

**Phase 2 - Important (Future Enhancement):**
1. Extract Doppler shifts from Sionna (`paths.doppler` property)
2. Add `doppler_hz` to `SinglePathInfo` dataclass
3. Adaptive update interval based on max Doppler spread
4. Coherence time calculation and display

**Phase 3 - Advanced (Out of Scope):**
1. CFR-based coherence bandwidth (more accurate)
2. Angular domain visualization (AoA/AoD scatter plots)
3. Historical channel metrics tracking
4. Link budget breakdown display

### Modified Files Summary

Based on wireless review, the following changes were made to the plan:

**src/sine/channel/server.py:**
- Added `calculate_k_factor()` helper function
- Enhanced path caching with wireless metrics
- Modified `/compute/single` to compute Bc and K-factor

**src/sine/channel/sionna_engine.py (future):**
- TODO: Extract Doppler information from `paths.doppler`
- TODO: Add `doppler_hz` field to `SinglePathInfo`

**scenes/viewer_live.ipynb:**
- Enhanced display function with channel analysis
- Frequency selectivity assessment (Bc vs BW)
- LOS/NLOS classification via K-factor
- Per-path details with Doppler (when available)

### Testing Validation Criteria

When implementing, verify:

1. **RMS Delay Spread**: Compare against Sionna debug output (`/debug/paths` endpoint)
2. **Coherence Bandwidth**: Validate Bc formula matches textbook values
3. **K-factor**:
   - LOS scenarios should show K > 10 dB
   - Indoor NLOS should show K < 0 dB or None
4. **Power Coverage**: Should be >90% for most scenarios with 5 paths
5. **Doppler**: Zero for static nodes, proportional to velocity for mobile

### References

Wireless formulas sourced from:
- Tse & Viswanath, "Fundamentals of Wireless Communication" (2005)
- Goldsmith, "Wireless Communications" (2005)
- 3GPP TR 38.901 (Channel modeling for 5G NR)
- Sionna RT documentation (delay spread, Doppler computation)
