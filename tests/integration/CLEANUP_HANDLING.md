# Integration Test Cleanup Handling

## Problem

When running integration tests with Ctrl+C, the session-scoped `channel_server` fixture's cleanup code (after `yield`) was not being executed, leaving:
- Channel server processes running (listening on port 8000)
- Deployed topologies/containers not destroyed
- GPU memory not released

## Solution

Added emergency cleanup handling using `atexit` and signal handlers (SIGINT, SIGTERM).

### How It Works

1. **Global tracking**:
   - `_deployed_topologies`: List of deployed topology paths
   - `_channel_server_process`: Reference to running channel server process

2. **Registration** (`_register_cleanup_handlers()`):
   - Called once on first deployment or channel server start
   - Registers `atexit` handler for normal exit
   - Registers signal handlers for SIGINT (Ctrl+C) and SIGTERM

3. **Automatic tracking**:
   - `deploy_topology()`: Automatically registers topologies
   - `destroy_topology()`: Automatically unregisters topologies
   - `channel_server`: Tracks server process

4. **Cleanup on exit** (`_cleanup_all()`):
   - Destroys all registered topologies (calls `sine destroy`)
   - Terminates channel server (SIGTERM, then SIGKILL if needed)
   - Called automatically on:
     - Normal test exit (atexit)
     - Ctrl+C (SIGINT handler)
     - Process termination (SIGTERM handler)

## Usage in Tests

Tests don't need to change! The cleanup is automatic:

```python
@pytest.mark.integration
def test_deployment(channel_server, examples_for_tests: Path):
    """The channel_server fixture ensures cleanup even if Ctrl+C."""
    yaml_path = examples_for_tests / "p2p_fallback_snr_vacuum" / "network.yaml"

    try:
        process = deploy_topology(yaml_path)  # Auto-registered
        # ... test logic
    finally:
        destroy_topology(yaml_path)  # Normal cleanup (unregisters)

    # If Ctrl+C happens before destroy_topology:
    # - Emergency cleanup will run
    # - Topology will be destroyed automatically
```

## Python `global` Keyword Notes

The code uses `global` keyword selectively:

### When `global` IS needed:
```python
def reassign_variable():
    global _my_var
    _my_var = None  # Reassigning the variable
```

### When `global` is NOT needed:
```python
def modify_inplace():
    # No global needed - modifying object in-place
    _my_list.append(item)      # Modifying list
    _my_list.remove(item)      # Modifying list
    _my_dict["key"] = value    # Modifying dict
```

### When `global` is NOT needed (reading):
```python
def read_variable():
    # No global needed - just reading
    if _my_var:
        print(_my_var)
```

## Manual Cleanup (if needed)

Before running tests, you can manually kill orphaned processes:

```bash
# Kill any orphaned channel servers
pkill -9 -f "sine channel-server"

# Verify they're gone
ps aux | grep "sine channel-server" | grep -v grep
```

## Testing the Cleanup

1. Start integration tests:
   ```bash
   UV_PATH=$(which uv) sudo -E $(which uv) run pytest tests/integration/point_to_point/ -v -s
   ```

2. Press Ctrl+C during deployment

3. Observe cleanup output:
   ```
   EMERGENCY CLEANUP (Ctrl+C or test interruption detected)
   ======================================================================

   Cleaning up 1 deployed topology(ies)...
     Destroying: /path/to/network.yaml

   Stopping channel server...
     ✓ Channel server stopped
   ======================================================================
   ```

4. Verify no orphans:
   ```bash
   ps aux | grep "sine channel-server"  # Should be empty
   docker ps | grep clab-                # Should be empty
   ```
