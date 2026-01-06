# Sionna v1.2.1 synthetic_array Indexing Fix

## Problem

The `get_path_details()` method was failing with:
```
ERROR: too many indices for array: array is 4-dimensional, but 6 were indexed
```

This occurred when trying to access path interactions and vertices using 6D/7D indexing patterns.

## Root Cause

**PathSolver default behavior**: When `PathSolver` is called without explicitly setting `synthetic_array`, it defaults to `True` (as of Sionna v1.2.1).

**Impact on array dimensions**:

| Configuration | `interactions` shape | `vertices` shape |
|--------------|---------------------|------------------|
| `synthetic_array=True` (default) | `[max_depth, num_rx, num_tx, num_paths]` (4D) | `[max_depth, num_rx, num_tx, num_paths, 3]` (5D) |
| `synthetic_array=False` | `[max_depth, num_rx, num_rx_ant, num_tx, num_tx_ant, num_paths]` (6D) | `[max_depth, num_rx, num_rx_ant, num_tx, num_tx_ant, num_paths, 3]` (7D) |

## What is synthetic_array?

From Sionna documentation:

> **When `synthetic_array=True`**: Transmitters and receivers are modeled as if they had a single antenna located at their position. The channel responses for each individual antenna of the arrays are then computed "synthetically" by applying appropriate phase shifts.

> **When `synthetic_array=False`**: Every transmit/receive antenna is modeled as a separate source/target of paths.

**Physical interpretation**:
- `True`: Aggregate channel between device centers (antennas collapsed into single effective channel)
- `False`: Individual per-antenna channels (full MIMO spatial information)

## Why synthetic_array=True is Correct for SiNE

SiNE is a **network emulation** framework, not a PHY-layer simulator. We care about:

1. **Aggregate channel statistics** - Overall SNR, BER, PER for the link
2. **Netem parameters** - Delay, jitter, loss%, rate at the packet level
3. **Computational efficiency** - Fewer dimensions = faster computation
4. **Simplicity** - Single effective channel per device pair

We do **NOT** need:
- Individual antenna element CSI
- Per-antenna beamforming weights
- Full MIMO spatial correlation matrices
- Antenna array calibration

**Conclusion**: `synthetic_array=True` is the appropriate choice for network emulation.

## Solution

Detect array dimensionality at runtime and apply correct indexing:

```python
# Check array dimensions to determine indexing pattern
use_synthetic_indexing = interactions.ndim == 4

# Access interactions
if use_synthetic_indexing:
    # synthetic_array=True: [max_depth, num_rx, num_tx, num_paths]
    path_interactions = interactions[:, 0, 0, i]
else:
    # synthetic_array=False: [max_depth, num_rx, num_rx_ant, num_tx, num_tx_ant, num_paths]
    path_interactions = interactions[:, 0, 0, 0, 0, i]

# Access vertices
if use_synthetic_indexing:
    # synthetic_array=True: [max_depth, num_rx, num_tx, num_paths, 3]
    path_verts = vertices[:, 0, 0, i, :]
else:
    # synthetic_array=False: [max_depth, num_rx, num_rx_ant, num_tx, num_tx_ant, num_paths, 3]
    path_verts = vertices[:, 0, 0, 0, 0, i, :]
```

## Changes Made

**File**: `src/sine/channel/sionna_engine.py`

1. **Added detection logic** (lines 416-424):
   - Check `interactions.ndim == 4` to determine if synthetic_array was used
   - Log the detected shape for debugging

2. **Updated indexing patterns** (lines 441-463):
   - Conditional indexing based on `use_synthetic_indexing` flag
   - Supports both 4D/5D (synthetic) and 6D/7D (non-synthetic) arrays

3. **Added documentation** (lines 151-154):
   - Explicit comment explaining PathSolver default behavior
   - Rationale for why synthetic_array=True is appropriate

## Verification

Test confirms the fix works:

```bash
✓ get_path_details() succeeded!
  TX position: (0, 0, 1)
  RX position: (10, 0, 1)
  Distance: 10.00 m
  Number of paths: 1
  Strongest path power: -66.73 dB
  Strongest path is LOS: True
  Strongest path delay: 0.00 ns
  Shortest path delay: 0.00 ns

SUCCESS: synthetic_array indexing fix works correctly!
```

## Future Considerations

### Option 1: Keep Current Approach (RECOMMENDED)
- Runtime detection makes code robust to both configurations
- No breaking changes required
- Works regardless of how PathSolver is called

### Option 2: Explicit Configuration
If you want to enforce synthetic_array explicitly:

```python
# In load_scene():
self.path_solver = PathSolver(synthetic_array=True)
```

This would make the configuration explicit but doesn't provide additional benefit since:
- Default is already True
- Runtime detection handles both cases anyway

### Option 3: Expose as Configuration Parameter
Allow users to choose via topology YAML:

```yaml
scene:
  file: scenes/vacuum.xml
  synthetic_array: true  # Optional, defaults to true
```

This is overkill for network emulation use cases.

## Recommendation

**Keep the current fix** - runtime detection with default synthetic_array=True behavior. This provides:
- Robustness to Sionna API changes
- Flexibility if we ever need non-synthetic arrays
- Clear documentation of behavior
- No user-facing configuration complexity

## References

- [Sionna RT: Understanding the Paths Object](https://nvlabs.github.io/sionna/api/rt.html#understanding-the-paths-object)
- [Sionna v1.2.1 Paths API Documentation](https://nvlabs.github.io/sionna/api/rt.html#paths)
- SiNE Issue: Array indexing error in `get_path_details()`

---

**Status**: ✅ FIXED in commit [pending]
**Date**: 2026-01-06
**Author**: Wireless Communications Engineer Agent
