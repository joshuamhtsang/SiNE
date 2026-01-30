# Claude Agent Instructions

## Running Commands with sudo

When a command requires `sudo` privileges:

**DO NOT execute sudo commands directly with the Bash tool.** Instead:

1. **Provide the full command** for the user to run manually using this pattern:
   ```bash
   UV_PATH=$(which uv) sudo -E $(which uv) run <command>
   ```
   This preserves the uv path in the sudo environment and works across different installation methods.

2. **Explain why sudo is needed** (e.g., "netem configuration requires sudo to access container network namespaces" or "integration tests need sudo to configure tc/qdisc on veth interfaces")

3. **Ask the user to run it** and provide the output

**Example response format:**
```
Please run the following command with sudo and share the output:

```bash
UV_PATH=$(which uv) sudo -E $(which uv) run pytest -s tests/integration/test_fallback_deployment.py
```

**Why sudo is needed:** Integration tests require sudo to configure netem (tc/qdisc) on container network namespaces via nsenter.
```

**Common sudo commands in SiNE:**
```bash
# Deploy topology (requires sudo for netem configuration)
UV_PATH=$(which uv) sudo -E $(which uv) run sine deploy examples/vacuum_20m/network.yaml

# Run integration tests (requires sudo for tc/qdisc and nsenter)
UV_PATH=$(which uv) sudo -E $(which uv) run pytest -s tests/integration/test_fallback_deployment.py

# Destroy topology (requires sudo to clean up containers and network namespaces)
UV_PATH=$(which uv) sudo -E $(which uv) run sine destroy examples/vacuum_20m/network.yaml
```

## Testing with pytest

When running pytest commands:
- Always add the `-s` flag for verbose output (captures stdout/stderr)
- Example: `uv run pytest -s tests/protocols/test_interference_engine.py`
- This helps with debugging test failures by showing print statements and logging
- Integration tests under `tests/integration/` always require sudo (use pattern above)

## Working with SiNE

- The project uses `uv` as the package manager (not pip/poetry)
- Sionna RT requires GPU for optimal performance but has CPU fallback
- Containerlab is a REQUIRED dependency (not optional)
- All wireless channel computations go through the FastAPI channel server
- MANET topologies can use point-to-point or shared bridge models
