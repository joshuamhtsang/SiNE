"""
YAML topology file loader with validation.

Loads network.yaml files and validates them against the Pydantic schema.
"""

from pathlib import Path
from typing import Union

import yaml
from pydantic import ValidationError

from sine.config.schema import NetworkTopology


class TopologyLoadError(Exception):
    """Error loading or parsing topology file."""

    pass


class TopologyLoader:
    """Load and validate network topology from YAML files."""

    def __init__(self, topology_path: Union[str, Path]):
        """
        Initialize loader with path to topology file.

        Args:
            topology_path: Path to network.yaml file
        """
        self.topology_path = Path(topology_path)
        if not self.topology_path.exists():
            raise TopologyLoadError(f"Topology file not found: {topology_path}")
        if not self.topology_path.is_file():
            raise TopologyLoadError(f"Not a file: {topology_path}")

    def load(self) -> NetworkTopology:
        """
        Load and validate topology from YAML file.

        Returns:
            Validated NetworkTopology object

        Raises:
            TopologyLoadError: If file cannot be parsed or validation fails
        """
        try:
            with open(self.topology_path) as f:
                raw_data = yaml.safe_load(f)
        except yaml.YAMLError as e:
            raise TopologyLoadError(f"YAML parse error: {e}") from e

        if not isinstance(raw_data, dict):
            raise TopologyLoadError("Topology file must contain a YAML mapping")

        try:
            topology = NetworkTopology.model_validate(raw_data)
        except ValidationError as e:
            # Format validation errors nicely
            errors = []
            for error in e.errors():
                loc = ".".join(str(x) for x in error["loc"])
                msg = error["msg"]
                errors.append(f"  {loc}: {msg}")
            error_msg = "\n".join(errors)
            raise TopologyLoadError(
                f"Topology validation failed:\n{error_msg}"
            ) from e

        return topology

    def load_raw(self) -> dict:
        """
        Load raw YAML data without validation.

        Useful for debugging or inspecting topology files.

        Returns:
            Raw dictionary from YAML file
        """
        with open(self.topology_path) as f:
            return yaml.safe_load(f)


def load_topology(path: Union[str, Path]) -> NetworkTopology:
    """
    Convenience function to load topology from file.

    Args:
        path: Path to network.yaml file

    Returns:
        Validated NetworkTopology object
    """
    loader = TopologyLoader(path)
    return loader.load()
