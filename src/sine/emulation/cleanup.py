"""
Generate cleanup script for SiNE emulation.

The cleanup script:
1. Stops and removes Docker containers
2. Removes veth pairs created by containerlab
3. Calls containerlab destroy
4. Cleans up any temporary files
"""

import stat
from pathlib import Path
from typing import Union

from sine.config.schema import NetworkTopology


CLEANUP_SCRIPT_TEMPLATE = '''#!/bin/bash
# SiNE Cleanup Script
# Auto-generated - do not edit manually
# Topology: {topology_name}
# Generated at: {timestamp}

set -e

echo "=== SiNE Cleanup: {topology_name} ==="

# Stop and remove Docker containers
echo "Removing containers..."
{container_commands}

# Call containerlab destroy if topology file exists
if [ -f "{clab_topology_path}" ]; then
    echo "Destroying containerlab topology..."
    containerlab destroy -t "{clab_topology_path}" --cleanup 2>/dev/null || true
fi

# Clean up temporary files
echo "Cleaning up temporary files..."
rm -f "{clab_topology_path}" 2>/dev/null || true

echo "=== Cleanup complete ==="
'''


class CleanupGenerator:
    """Generate cleanup.sh script for SiNE emulation."""

    def __init__(self, config: NetworkTopology):
        """
        Initialize generator with topology config.

        Args:
            config: NetworkTopology configuration
        """
        self.config = config

    def generate(self, output_path: Union[str, Path]) -> Path:
        """
        Generate cleanup script.

        Args:
            output_path: Path to write cleanup.sh

        Returns:
            Path to generated script
        """
        import datetime

        output_path = Path(output_path)
        topology_name = self.config.name
        prefix = self.config.container_prefix

        # Generate container removal commands
        container_commands = []
        for node_name in self.config.topology.nodes.keys():
            container_name = f"{prefix}-{topology_name}-{node_name}"
            container_commands.append(
                f'docker stop "{container_name}" 2>/dev/null || true'
            )
            container_commands.append(
                f'docker rm "{container_name}" 2>/dev/null || true'
            )

        # Path to containerlab topology file
        clab_topology_path = output_path.parent / ".sine_clab_topology.yaml"

        # Generate script content
        script_content = CLEANUP_SCRIPT_TEMPLATE.format(
            topology_name=topology_name,
            timestamp=datetime.datetime.now().isoformat(),
            container_commands="\n".join(container_commands),
            clab_topology_path=clab_topology_path,
        )

        # Write script
        with open(output_path, "w") as f:
            f.write(script_content)

        # Make executable (chmod +x)
        output_path.chmod(output_path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

        return output_path


def generate_cleanup_script(
    config: NetworkTopology, output_path: Union[str, Path]
) -> Path:
    """
    Convenience function to generate cleanup script.

    Args:
        config: NetworkTopology configuration
        output_path: Path to write cleanup.sh

    Returns:
        Path to generated script
    """
    generator = CleanupGenerator(config)
    return generator.generate(output_path)
