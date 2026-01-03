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

Update the existing `/compute/single` endpoint to store path details:

```python
@app.post("/compute/single", response_model=ChannelResponse)
async def compute_single_channel(request: WirelessLinkRequest) -> ChannelResponse:
    global _engine, _mcs_tables, _path_cache, _device_positions

    # ... [existing computation code] ...

    # NEW: Before clear_devices(), cache the path details
    try:
        path_details = _engine.get_path_details()

        # Store in cache with link identifier
        link_id = f"{request.tx_node}:{tx_node}->{request.rx_node}:{rx_node}"

        # Limit to 5 strongest paths for visualization
        sorted_paths = sorted(path_details.paths, key=lambda p: p.power_db, reverse=True)
        limited_paths = sorted_paths[:5]

        # Convert to JSON-serializable format
        paths_data = [{
            "delay_ns": float(p.delay_ns),
            "power_db": float(p.power_db),
            "vertices": [[float(v[0]), float(v[1]), float(v[2])] for v in p.vertices],
            "interaction_types": p.interaction_types,
            "is_los": p.is_los
        } for p in limited_paths]

        _path_cache[link_id] = {
            "tx_name": f"{request.tx_node}:{tx_node}",
            "rx_name": f"{request.rx_node}:{rx_node}",
            "tx_position": [tx_pos[0], tx_pos[1], tx_pos[2]],
            "rx_position": [rx_pos[0], rx_pos[1], rx_pos[2]],
            "distance_m": float(path_details.distance_m),
            "num_paths_total": path_details.num_paths,
            "num_paths_returned": len(paths_data),
            "paths": paths_data
        }

        # Also store device positions
        _device_positions[f"{request.tx_node}:{tx_node}"] = tx_pos
        _device_positions[f"{request.rx_node}:{rx_node}"] = rx_pos

    except Exception as e:
        logger.warning(f"Failed to cache paths for visualization: {e}")

    # ... [rest of existing code] ...
    return ChannelResponse(...)  # Existing return
```

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
# GET /api/visualization/state Response:
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
      "num_paths_returned": int,   # Limited to 5 strongest
      "paths": [
        {
          "delay_ns": float,
          "power_db": float,
          "vertices": [[x, y, z], ...],
          "interaction_types": [str],
          "is_los": bool
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

**Cell 3: Rendering Functions**
```python
def display_visualization(viz_state, metrics=None):
    """Display visualization state and optional metrics."""
    print(f"=== Visualization State (Cache: {viz_state['cache_size']} links) ===\n")

    # Display device positions
    print("Devices:")
    for device in viz_state["devices"]:
        pos = device["position"]
        print(f"  {device['name']}: ({pos['x']:.1f}, {pos['y']:.1f}, {pos['z']:.1f})")

    # Display path information
    print(f"\nPaths ({len(viz_state['paths'])} links):")
    for path_data in viz_state["paths"]:
        print(f"  {path_data['tx_name']} → {path_data['rx_name']}")
        print(f"    Distance: {path_data['distance_m']:.1f} m")
        print(f"    Paths: {path_data['num_paths_returned']}/{path_data['num_paths_total']}")

    # Display optional metrics
    if metrics:
        print("\n=== Link Metrics ===")
        for link in metrics.get("links", []):
            print(f"\n{link['tx']} ↔ {link['rx']}")
            print(f"  Rate: {link['rate_mbps']:.1f} Mbps")
            print(f"  Loss: {link['loss_percent']:.2f}%")
            print(f"  SNR: {link.get('snr_db', 'N/A')} dB")
            if link.get('modulation'):
                print(f"  Modulation: {link['modulation']}")
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

1. **`src/sine/channel/server.py`** (MAIN - Caching & new endpoint)
   - Add global variables: `_path_cache`, `_device_positions`
   - Modify `/compute/single` to cache paths after computation
   - Add new endpoint: `GET /api/visualization/state`

2. **`src/sine/channel/sionna_engine.py`** (Minor enhancement)
   - Store `self.scene_path` in `load_scene()` method for later reference

3. **`src/sine/mobility/api.py`** (OPTIONAL - metrics endpoint)
   - Optionally add `GET /api/emulation/metrics` endpoint

4. **`scenes/viewer_live.ipynb`** (New file)
   - Simple Jupyter notebook that polls `/api/visualization/state`
   - Displays cached paths and device positions
   - No computation in notebook

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
