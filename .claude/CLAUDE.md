# Claude Agent Instructions

## Running Commands with sudo

When a command requires `sudo` privileges:
- Provide the full command for the user to run manually
- Explain why sudo is needed (e.g., "netem configuration requires sudo to access container network namespaces")
- Ask the user to run it and provide the output
- Example: "Please run the following command with sudo and share the output:"

## Testing with pytest

When running pytest commands:
- Always add the `-s` flag for verbose output (captures stdout/stderr)
- Example: `uv run pytest -s tests/protocols/test_interference_engine.py`
- This helps with debugging test failures by showing print statements and logging

## Working with SiNE

- The project uses `uv` as the package manager (not pip/poetry)
- Sionna RT requires GPU for optimal performance but has CPU fallback
- Containerlab is a REQUIRED dependency (not optional)
- All wireless channel computations go through the FastAPI channel server
- MANET topologies can use point-to-point or shared bridge models
