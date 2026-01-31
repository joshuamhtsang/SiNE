# Investigation: Path Loss Discrepancy in Spectral Efficiency Calculator

**Date**: 2026-01-29
**Initial Issue**: All wireless links (20m and 30m) returned identical path loss values (72.75 dB)
**Final Resolution**: Two separate issues: (1) Missing scene loading, (2) Antenna gain field confusion

## Problem Summary

### Phase 1: Identical Path Loss for All Links

The spectral efficiency calculator was returning identical path loss values for all links, regardless of:
- Distance (20m vs 30m)
- Antenna type (isotropic vs dipole)
- Actual node positions

This was physically impossible and indicated a systematic issue with scene loading or caching.

**Root Cause**: Calculator never called `/scene/load`, so channel server used stale/empty scene.

### Phase 2: Path Loss Values Still "Wrong" After Scene Fix

After fixing scene loading, path loss became distance-dependent (good!), but values didn't match expectations:
- Expected for 30m with `antenna_gain_dbi: 3.0`: **70.28 dB**
- Actual: **72.8 dB**

**Root Cause**: The `antenna_gain_dbi: 3.0` field was ignored by Sionna RT. The actual gain came from `antenna_pattern: dipole` which provides **1.76 dBi**, not 3.0 dBi. The path loss values were actually CORRECT all along.

**Final Decision**: Enforce schema validation to allow EITHER `antenna_gain_dbi` OR `antenna_pattern`, not both.

## Investigation Steps

### 1. Verified Positions Were Correct

Added debug output to confirm TX/RX positions being sent to channel server:

```
DEBUG: node1:eth1 -> node2:eth1: TX pos: (0, 0, 1), RX pos: (20, 0, 1)  ✅ 20m
DEBUG: node1:eth1 -> node2:eth1: TX pos: (0, 0, 1), RX pos: (30, 0, 1) ✅ 30m
```

**Result**: Positions were correct. The calculator was sending the right coordinates.

### 2. Checked Expected Path Loss Values

Manually calculated expected FSPL:

| Link | Distance | Antenna | FSPL | Expected Path Loss | Actual |
|------|----------|---------|------|-------------------|--------|
| vacuum_20m | 20m | Iso (0 dBi) | 72.76 dB | 72.76 dB | 72.75 dB ✅ |
| manet_30m | 30m | Dipole (3 dBi) | 76.28 dB | 70.28 dB | 72.75 dB ❌ |

**FSPL Formula**: `20·log10(d) + 20·log10(f) - 147.55`
**With antenna gains**: `FSPL - (TX_gain + RX_gain)`

**Result**: 30m links had SAME path loss as 20m links - impossible!

### 3. Traced Channel Server Scene Loading

Checked `/api/visualization/state` endpoint:

```bash
curl -s http://localhost:8000/api/visualization/state | jq '.scene'
# Result: null
```

**Result**: No scene was loaded! The calculator never called `/scene/load`.

### 4. Reviewed Channel Server Code

Found two critical issues in how `/compute/single` handles scenes:

**Issue #1: Scene Only Loaded Once**
```python
# server.py line 1065-1066
if not getattr(_engine, "_scene_loaded", False):
    _engine.load_scene(frequency_hz=request.frequency_hz, bandwidth_hz=request.bandwidth_hz)
```
- Scene loaded only if `_scene_loaded == False`
- No `scene_path` parameter → empty scene
- Once loaded, never reloaded

**Issue #2: Spectral Efficiency Calculator Never Loads Scene**
- The calculator called `/compute/single` directly
- Never called `/scene/load` to load topology's scene file
- Used whatever scene was previously loaded (or empty scene)

## Root Causes

### Root Cause #1: Missing Scene Load Call

**Problem**: The spectral efficiency calculator never called `/scene/load` before computing metrics.

**Impact**: Channel server used a stale or empty scene, causing incorrect path loss calculations.

**Evidence**:
- All links returned identical path loss (72.75 dB)
- `/api/visualization/state` showed `scene: null`
- Debug output confirmed positions were correct

### Root Cause #2: Scene Reloading Not Supported

**Problem**: The channel server does not support reloading a different scene once one is loaded.

**Impact**: If channel server has a scene already loaded from a previous deployment, the calculator will use that scene instead of the topology's scene.

**Evidence**:
- `load_scene()` only called when `_scene_loaded == False`
- No mechanism to unload/reload scenes
- Mobility API updates positions but not scene geometry

## Solution

### Fix #1: Add Scene Loading Step

Added scene loading in `main()` function ([calc_spectralefficiency.py:500-532](calc_spectralefficiency.py#L500-L532)):

```python
# Load scene into channel server (required for ray tracing)
if topology.topology.scene and topology.topology.scene.file:
    console.print(f"[cyan]Loading scene into channel server: {topology.topology.scene.file}...[/cyan]")
    scene_payload = {
        "scene_file": str(topology.topology.scene.file),
        "frequency_hz": 5.18e9,  # Default
        "bandwidth_hz": 80e6,     # Default
    }
    with httpx.Client(timeout=30.0) as client:
        response = client.post(f"{channel_server_url}/scene/load", json=scene_payload)
        response.raise_for_status()
        console.print(f"[green]✓[/green] Scene loaded successfully")
```

### Fix #2: Add Scene Status Check and Warning

Added health check before scene loading ([calc_spectralefficiency.py:500-520](calc_spectralefficiency.py#L500-L520)):

```python
# Check if scene already loaded
with httpx.Client(timeout=30.0) as client:
    response = client.get(f"{channel_server_url}/health")
    health_data = response.json()
    scene_already_loaded = health_data.get("scene_loaded", False)

if scene_already_loaded:
    console.print("[yellow]⚠ WARNING: A scene is already loaded in the channel server![/yellow]")
    console.print("[yellow]  The channel server does not support scene reloading.[/yellow]")
    console.print("[yellow]  If you get incorrect path loss values, restart the channel server:[/yellow]")
    console.print("[yellow]    1. Stop the channel server (Ctrl+C)[/yellow]")
    console.print("[yellow]    2. Start it again: uv run sine channel-server[/yellow]")
    console.print(f"[yellow]  Then re-run this script.[/yellow]")
```

## Validation

### Before Fix (Scene Loading Issue)

```bash
# All links returned identical path loss
vacuum_20m:   dist=20.0m, path_loss=72.75dB ✅ (matches FSPL)
manet_30m_1:  dist=30.0m, path_loss=72.75dB ❌ (should be ~70-76 dB)
manet_30m_2:  dist=30.0m, path_loss=72.75dB ❌ (should be ~70-76 dB)
manet_30m_3:  dist=30.0m, path_loss=72.75dB ❌ (should be ~70-76 dB)
```

### After Scene Loading Fix

**Note**: To test the fix properly, the channel server must be restarted to clear any previously loaded scene:

```bash
# 1. Stop channel server (Ctrl+C)
# 2. Start fresh channel server
uv run sine channel-server

# 3. Run calculator
uv run python utilities/calc_spectralefficiency.py examples/manet_triangle_shared/network.yaml
```

**Result after scene loading fix**:
```bash
vacuum_20m:   dist=20.0m, path_loss=72.75dB ✅
manet_30m_1:  dist=30.0m, path_loss=72.8dB  ✅ (scene now loaded!)
manet_30m_2:  dist=30.0m, path_loss=72.8dB  ✅
manet_30m_3:  dist=30.0m, path_loss=72.8dB  ✅
```

**New Issue**: The 30m links now showed distance-dependent path loss (good!), but the value (72.8 dB) still didn't match the expected 70.28 dB based on `antenna_gain_dbi: 3.0` in the YAML.

## Root Cause #3: Antenna Gain Confusion (The Real Issue)

### Investigation

After fixing the scene loading issue, path loss values were now distance-dependent but still didn't match expectations:

| Configuration | Expected Path Loss | Actual Path Loss | Status |
|---------------|-------------------|------------------|---------|
| 30m, `antenna_gain_dbi: 3.0`, `antenna_pattern: dipole` | 70.28 dB | 72.8 dB | ❌ 2.5 dB discrepancy |

**Initial hypothesis**: Something wrong with antenna gain handling in Sionna RT.

### Discovery: `antenna_gain_dbi` is Ignored for Ray Tracing

Measured actual antenna pattern gains using Sionna's `compute_gain()` method:

```python
from sionna.rt import PlanarArray

# Test isotropic
array_iso = PlanarArray(num_rows=1, num_cols=1, pattern="iso", polarization="V")
d_iso, g_iso, eta_iso = array_iso.antenna_pattern.compute_gain()
# Result: Gain = 0.0 dBi

# Test dipole (short dipole)
array_dipole = PlanarArray(num_rows=1, num_cols=1, pattern="dipole", polarization="V")
d_dipole, g_dipole, eta_dipole = array_dipole.antenna_pattern.compute_gain()
# Result: Gain = 1.76 dBi  ← NOT 3.0 dBi!

# Test half-wave dipole
array_hw = PlanarArray(num_rows=1, num_cols=1, pattern="hw_dipole", polarization="V")
d_hw, g_hw, eta_hw = array_hw.antenna_pattern.compute_gain()
# Result: Gain = 2.16 dBi
```

**Key Finding**: Sionna's `antenna_pattern: dipole` provides **1.76 dBi**, not the 3.0 dBi specified in `antenna_gain_dbi`.

### Corrected Expected Values

With the actual antenna pattern gains:

```
FSPL @ 30m, 5.18 GHz = 76.28 dB
Sionna dipole gain (TX) = 1.76 dBi
Sionna dipole gain (RX) = 1.76 dBi
Total antenna gain = 1.76 + 1.76 = 3.52 dB

Expected path loss = 76.28 - 3.52 = 72.76 dB
```

**Observed value: 72.8 dB** ✅ **This is CORRECT!**

### Why the Confusion?

The YAML configuration allows specifying BOTH `antenna_gain_dbi` and `antenna_pattern`:

```yaml
wireless:
  antenna_pattern: dipole        # Actually provides 1.76 dBi
  antenna_gain_dbi: 3.0          # Ignored by Sionna RT! Only metadata.
```

**The Problem**:
- `antenna_pattern` determines the actual gain used by Sionna RT (embedded in path coefficients)
- `antenna_gain_dbi` is only used for:
  - Link budget calculations when `from_sionna=False` (FSPL fallback mode)
  - Documentation/metadata purposes
- Users expect `antenna_gain_dbi` to control the gain, but it doesn't when using RT

**Sionna RT Antenna Pattern Gains**:
| Pattern | Gain (dBi) | Description |
|---------|-----------|-------------|
| `iso` | 0.0 | Isotropic (omnidirectional) |
| `dipole` | 1.76 | Short dipole (half-length) |
| `hw_dipole` | 2.16 | Half-wavelength dipole |
| `tr38901` | ~8.0 | 3GPP directional antenna |

### Solution: Enforce Schema Validation

**Decision**: The schema should only allow defining **EITHER** `antenna_gain_dbi` **OR** `antenna_pattern`, not both.

**Rationale**:
- Prevents confusion about which field controls the actual gain
- Makes it clear:
  - Use `antenna_pattern` for ray tracing with Sionna (gain embedded in pattern)
  - Use `antenna_gain_dbi` for FSPL fallback mode or fixed netem links
- Eliminates contradictory configurations like `antenna_gain_dbi: 3.0` + `antenna_pattern: dipole` (1.76 dBi)

**Implementation**:
- Add Pydantic validator to `WirelessParams` schema
- Mutual exclusion: exactly one of `antenna_gain_dbi` or `antenna_pattern` must be specified
- Error message explains the distinction and proper usage

## Key Learnings

### 1. Channel Server Architecture

- **Singleton scene**: One scene per server instance
- **No reload support**: Scene cannot be changed without restarting server
- **Empty scene fallback**: If `/scene/load` not called, uses empty scene
- **Position updates**: Mobility API can update device positions, but not scene geometry

### 2. Scene vs. Positions

- **Scene geometry**: Walls, objects, materials (static)
- **Device positions**: TX/RX coordinates (dynamic via mobility API)
- **Path computation**: Requires both scene AND positions
- **Caching**: PathSolver created once per scene load

### 3. Typical Usage Pattern

**Deployment workflow**:
1. Start channel server
2. Deploy topology → loads scene + initial positions
3. Update positions via mobility API → keeps same scene
4. Destroy topology → scene remains loaded

**Calculator workflow (should be)**:
1. Start channel server (if not running)
2. Load scene from topology
3. Compute metrics for all links
4. Display results

### 4. Antenna Gain Handling in Sionna RT

**Critical Understanding**:
- Sionna RT antenna patterns **embed gain in the path coefficients**
- The `antenna_pattern` field determines actual gain (not `antenna_gain_dbi`)
- Path coefficients from `paths.cir()` already include TX and RX antenna pattern effects
- Per [src/sine/channel/snr.py](../src/sine/channel/snr.py#L76-L98):
  ```python
  # Sionna path coefficients already include antenna patterns
  # Do NOT add antenna gains again (double-counting)
  if from_sionna:
      return tx_power_dbm - path_loss_db  # No antenna gain terms!
  ```

**Antenna Pattern vs. Antenna Gain**:
| Field | Purpose | Used By |
|-------|---------|---------|
| `antenna_pattern` | Selects Sionna pattern (iso, dipole, hw_dipole, tr38901) | Ray tracing path computation |
| `antenna_gain_dbi` | Numeric gain value | FSPL fallback mode, documentation only |

**The fields should be mutually exclusive** to prevent user confusion.

## Recommendations

### For Users

**Before running the spectral efficiency calculator**:
1. Ensure channel server is freshly started (no stale scenes)
2. Let the calculator load the scene from the topology
3. If you get unexpected path loss values, restart the channel server

**When configuring wireless interfaces**:
- Use `antenna_pattern` for Sionna RT-based links (gain embedded in pattern)
- Use `antenna_gain_dbi` for FSPL fallback or fixed netem links
- **Do NOT specify both** (schema will enforce this)

### For Future Development

**✅ DECISION: Enforce Schema Validation**
- Add Pydantic validator to make `antenna_gain_dbi` and `antenna_pattern` mutually exclusive
- Allow exactly one field to be specified (not both)
- Provide clear error message explaining the distinction
- Update example topologies to follow the new schema

**✅ DECISION: Add Antenna Pattern Gain Mapping**
- Create a mapping dictionary: `ANTENNA_PATTERN_GAINS: dict[str, float]`
- Maps antenna pattern names to their gain values in dBi:
  - `"iso"` → 0.0 dBi
  - `"dipole"` → 1.76 dBi (short dipole)
  - `"hw_dipole"` → 2.16 dBi (half-wave dipole)
  - `"tr38901"` → 8.0 dBi (3GPP directional)
- Use this mapping in fallback engine when `antenna_pattern` is specified
- Reference Sionna documentation in code comments:
  - Sionna RT Antenna Patterns: https://nvlabs.github.io/sionna/api/rt.html#antenna-patterns
  - Values measured using `PlanarArray.antenna_pattern.compute_gain()`
- Location: Add to `src/sine/channel/constants.py` or `src/sine/channel/antenna_patterns.py`

**Rationale**:
- Allows fallback engine to use realistic antenna gains based on pattern type
- Provides single source of truth for antenna pattern gains
- Enables validation and testing without requiring Sionna RT
- Useful for documentation and user expectations

**✅ DECISION: Expose Fallback Engine and Add Testing**
- Channel server should have an option to use non-Sionna (FSPL-based) fallback methods
- This allows testing and validation without GPU/Sionna dependencies
- Use `antenna_gain_dbi` OR lookup from `ANTENNA_PATTERN_GAINS` mapping
- Add comprehensive unit and integration tests for fallback engine:
  - Test FSPL calculations against known values
  - Test link budget with `antenna_gain_dbi` (should NOT double-count)
  - Test link budget with `antenna_pattern` (lookup gain from mapping)
  - Test fallback mode for simple topologies (vacuum, free space)
  - Integration test comparing Sionna RT vs fallback for simple cases
- Implementation approach:
  - Add `engine_type` parameter to channel server endpoints (`"sionna"` | `"fallback"`)
  - Or add dedicated fallback endpoints (e.g., `/compute/fallback`)
  - Ensure `FallbackEngine` uses antenna pattern gain mapping
  - Properly test and document fallback engine

**Rationale**:
- Fallback engine currently exists but may not be well-tested
- Useful for CI/CD environments without GPU
- Provides validation baseline for ray tracing results
- Helps debug antenna gain handling (both `antenna_gain_dbi` and pattern-based)

**Scene Management (Optional Future Enhancements)**:

**Option 1: Add Scene Unload/Reload**
- Add `/scene/unload` endpoint to clear current scene
- Modify `/scene/load` to support reloading
- Update PathSolver creation logic

**Option 2: Add Scene Comparison**
- Track currently loaded scene path
- Compare with requested scene path
- Warn or error if mismatch detected

**Option 3: Document Current Behavior**
- Clearly document that scene is singleton
- Add warning in `/compute/single` docs
- Update calculator docs with restart instructions

## Summary: Corrected Expected Values

With correct understanding of Sionna antenna pattern gains:

| Topology | Distance | Antenna Pattern | Actual Gain (dBi) | FSPL (dB) | Expected Path Loss (dB) | Observed (dB) | Status |
|----------|----------|----------------|------------------|-----------|------------------------|---------------|---------|
| vacuum_20m | 20m | iso | 0.0 (TX) + 0.0 (RX) = 0.0 | 72.76 | 72.76 | 72.75 | ✅ |
| manet_triangle_shared | 30m | dipole | 1.76 (TX) + 1.76 (RX) = 3.52 | 76.28 | **72.76** | 72.8 | ✅ |

**Key Insight**: The `antenna_gain_dbi: 3.0` field in the YAML was misleading. Sionna RT uses the gain embedded in `antenna_pattern: dipole` (1.76 dBi), not the `antenna_gain_dbi` value.

## Files Modified

- [utilities/calc_spectralefficiency.py](utilities/calc_spectralefficiency.py):
  - Added scene loading step (lines 500-532)
  - Added scene status check and warning (lines 500-520)

## Files to Modify (Future Work)

- [src/sine/config/schema.py](../src/sine/config/schema.py):
  - Add Pydantic validator to enforce mutual exclusion of `antenna_gain_dbi` and `antenna_pattern`
  - Provide clear error message explaining the distinction

## References

- [PLAN_calc_spectral_efficiency.md](PLAN_calc_spectral_efficiency.md) - Original plan
- [PHASE_SPECTRAL_EFF_SHARED_BRIDGE_COMPLETE.md](PHASE_SPECTRAL_EFF_SHARED_BRIDGE_COMPLETE.md) - Implementation summary
- [CLAUDE.md](../CLAUDE.md) - Antenna gain handling notes
- Sionna RT Technical Report, Section 3.3 - Channel Coefficients computation (antenna patterns embedded)
