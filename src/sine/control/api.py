"""
Control API Server for SiNE.

Provides REST API endpoints for controlling the emulation at runtime.
This allows external tools, scripts, or interactive interfaces to
control node positions and other emulation parameters in real-time.

Example usage:
    # Start the control API server
    uv run sine control-server --topology examples/vacuum_20m/network.yaml

    # Update position via HTTP
    curl -X POST http://localhost:8002/api/control/update \
         -H "Content-Type: application/json" \
         -d '{"node": "node1", "x": 10.0, "y": 5.0, "z": 1.5}'
"""

import asyncio
import logging
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
import uvicorn

from sine.emulation.controller import EmulationController

logger = logging.getLogger(__name__)


class PositionUpdate(BaseModel):
    """Request model for position updates."""

    node: str = Field(..., description="Node name to update")
    x: float = Field(..., description="X coordinate in meters")
    y: float = Field(..., description="Y coordinate in meters")
    z: float = Field(default=1.0, description="Z coordinate in meters (height)")


class PositionResponse(BaseModel):
    """Response model for position updates."""

    status: str
    node: str
    position: dict[str, float]
    message: Optional[str] = None


class InterfaceActiveUpdate(BaseModel):
    """Request model for toggling interface active state."""

    node: str = Field(..., description="Node name")
    interface: str = Field(..., description="Interface name (e.g. 'eth1')")
    is_active: bool = Field(..., description="True to enable, False to disable")


class InterfaceStateResponse(BaseModel):
    """Response model for interface state queries and updates."""

    status: str
    node: str
    interface: str
    is_active: bool
    message: Optional[str] = None


class RecomputeResponse(BaseModel):
    """Response model for forced channel recompute."""

    status: str
    message: Optional[str] = None


class ControlAPIServer:
    """
    REST API server for emulation runtime control.

    Wraps an EmulationController and exposes endpoints for controlling
    node positions and other emulation parameters.
    """

    def __init__(self, topology_path: Path):
        """
        Initialize control API server.

        Args:
            topology_path: Path to network.yaml topology file
        """
        self.topology_path = topology_path
        self.controller: Optional[EmulationController] = None
        self.app = FastAPI(
            title="SiNE Control API",
            description="Control wireless network emulation at runtime",
            version="0.1.0",
        )

        # Register routes
        self._register_routes()

    def _register_routes(self) -> None:
        """Register API routes."""

        @self.app.get("/health")
        async def health():
            """Health check endpoint."""
            if self.controller and self.controller._running:
                return {
                    "status": "healthy",
                    "emulation": "running",
                    "topology": str(self.topology_path),
                }
            return {
                "status": "degraded",
                "emulation": "not running",
                "message": "Emulation not started or has stopped",
            }

        @self.app.post("/api/control/update", response_model=PositionResponse)
        async def update_position(update: PositionUpdate):
            """
            Update a node's position.

            This triggers:
            1. Position update in configuration
            2. Channel recomputation with new positions
            3. Netem reconfiguration with new channel conditions

            The update typically completes in ~100ms.
            """
            if not self.controller or not self.controller._running:
                raise HTTPException(
                    status_code=503,
                    detail="Emulation not running. Start with /api/emulation/start",
                )

            # Validate node exists
            if update.node not in self.controller.config.topology.nodes:
                available_nodes = list(self.controller.config.topology.nodes.keys())
                raise HTTPException(
                    status_code=404,
                    detail=f"Node '{update.node}' not found. "
                    f"Available nodes: {available_nodes}",
                )

            # Validate node has wireless capability and find wireless interfaces
            node_config = self.controller.config.topology.nodes[update.node]
            wireless_interfaces = []
            if node_config.interfaces:
                wireless_interfaces = [
                    iface_name
                    for iface_name, iface in node_config.interfaces.items()
                    if iface.is_wireless
                ]

            if not wireless_interfaces:
                raise HTTPException(
                    status_code=400,
                    detail=f"Node '{update.node}' does not have wireless capability",
                )

            try:
                # Update position for all wireless interfaces on this node
                for iface_name in wireless_interfaces:
                    await self.controller.update_node_position(
                        update.node, iface_name, update.x, update.y, update.z
                    )

                return PositionResponse(
                    status="success",
                    node=update.node,
                    position={"x": update.x, "y": update.y, "z": update.z},
                    message=f"Position updated and channels recomputed",
                )

            except Exception as e:
                logger.error(f"Failed to update position: {e}")
                raise HTTPException(status_code=500, detail=str(e))

        @self.app.get("/api/control/position/{node}")
        async def get_position(node: str):
            """Get current position of a node."""
            if not self.controller or not self.controller._running:
                raise HTTPException(status_code=503, detail="Emulation not running")

            if node not in self.controller.config.topology.nodes:
                raise HTTPException(status_code=404, detail=f"Node '{node}' not found")

            node_config = self.controller.config.topology.nodes[node]

            # Find first wireless interface for position query
            wireless_iface = None
            if node_config.interfaces:
                for iface in node_config.interfaces.values():
                    if iface.is_wireless:
                        wireless_iface = iface
                        break

            if not wireless_iface:
                raise HTTPException(
                    status_code=400, detail=f"Node '{node}' has no wireless capability"
                )

            pos = wireless_iface.wireless.position
            return {
                "node": node,
                "position": {"x": pos.x, "y": pos.y, "z": pos.z},
            }

        @self.app.post("/api/control/recompute", response_model=RecomputeResponse)
        async def force_recompute():
            """
            Force an immediate recompute of all link channels.

            Useful after external state changes or as a diagnostic trigger.
            Equivalent to re-deploying channel conditions without changing positions.
            Typically completes in <100ms (GPU) or <500ms (CPU fallback).
            """
            if not self.controller or not self.controller._running:
                raise HTTPException(status_code=503, detail="Emulation not running")

            try:
                await self.controller.force_channel_recompute()
                return RecomputeResponse(
                    status="success",
                    message="All link channels recomputed",
                )
            except Exception as e:
                logger.error(f"Forced recompute failed: {e}")
                raise HTTPException(status_code=500, detail=str(e))

        @self.app.post("/api/control/interface", response_model=InterfaceStateResponse)
        async def set_interface_active(update: InterfaceActiveUpdate):
            """
            Enable or disable a wireless interface at runtime.

            When disabled, the interface is excluded from SINR interference calculations.
            Triggers a channel recompute. The physical link remains in the topology.
            """
            if not self.controller or not self.controller._running:
                raise HTTPException(status_code=503, detail="Emulation not running")

            # Validate node exists
            if update.node not in self.controller.config.topology.nodes:
                available = list(self.controller.config.topology.nodes.keys())
                raise HTTPException(
                    status_code=404,
                    detail=f"Node '{update.node}' not found. Available: {available}",
                )

            # Validate interface exists and is wireless
            node_config = self.controller.config.topology.nodes[update.node]
            if not node_config.interfaces or update.interface not in node_config.interfaces:
                raise HTTPException(
                    status_code=404,
                    detail=f"Interface '{update.interface}' not found on node '{update.node}'",
                )
            iface_config = node_config.interfaces[update.interface]
            if not iface_config.is_wireless:
                raise HTTPException(
                    status_code=400,
                    detail=f"Interface '{update.interface}' is not wireless (fixed_netem cannot be toggled)",
                )

            try:
                await self.controller.update_interface_active(
                    update.node, update.interface, update.is_active
                )
                action = "enabled" if update.is_active else "disabled"
                return InterfaceStateResponse(
                    status="success",
                    node=update.node,
                    interface=update.interface,
                    is_active=update.is_active,
                    message=f"Interface {action} and channels recomputed",
                )
            except Exception as e:
                logger.error(f"Failed to set interface active state: {e}")
                raise HTTPException(status_code=500, detail=str(e))

        @self.app.get(
            "/api/control/interface/{node}/{interface}",
            response_model=InterfaceStateResponse,
        )
        async def get_interface_state(node: str, interface: str):
            """Get the current active state of a specific wireless interface."""
            if not self.controller or not self.controller._running:
                raise HTTPException(status_code=503, detail="Emulation not running")

            if node not in self.controller.config.topology.nodes:
                raise HTTPException(status_code=404, detail=f"Node '{node}' not found")

            node_config = self.controller.config.topology.nodes[node]
            if not node_config.interfaces or interface not in node_config.interfaces:
                raise HTTPException(
                    status_code=404,
                    detail=f"Interface '{interface}' not found on node '{node}'",
                )
            iface_config = node_config.interfaces[interface]
            if not iface_config.is_wireless:
                raise HTTPException(
                    status_code=400,
                    detail=f"Interface '{interface}' is not wireless",
                )

            return InterfaceStateResponse(
                status="ok",
                node=node,
                interface=interface,
                is_active=iface_config.wireless.is_active,
            )

        @self.app.get("/api/nodes")
        async def list_nodes():
            """List all nodes with their current positions."""
            if not self.controller or not self.controller._running:
                raise HTTPException(status_code=503, detail="Emulation not running")

            nodes = []
            for name, config in self.controller.config.topology.nodes.items():
                # Find first wireless interface
                if config.interfaces:
                    for iface in config.interfaces.values():
                        if iface.is_wireless:
                            pos = iface.wireless.position
                            nodes.append(
                                {
                                    "name": name,
                                    "position": {"x": pos.x, "y": pos.y, "z": pos.z},
                                }
                            )
                            break  # Only add each node once (using first wireless interface)
            return {"nodes": nodes}

    async def start(self, host: str = "0.0.0.0", port: int = 8002) -> None:
        """
        Start the control API server and emulation.

        Args:
            host: Host to bind to (default: 0.0.0.0)
            port: Port to bind to (default: 8002)
        """
        logger.info(f"Starting control API server on {host}:{port}")

        # Initialize and start emulation controller
        self.controller = EmulationController(self.topology_path)
        await self.controller.start()

        logger.info("Emulation started, starting API server")

        # Start FastAPI server
        config = uvicorn.Config(
            self.app, host=host, port=port, log_level="info", access_log=False
        )
        server = uvicorn.Server(config)

        try:
            await server.serve()
        except KeyboardInterrupt:
            logger.info("Shutting down control API server")
        finally:
            if self.controller:
                await self.controller.stop()


async def run_control_server(
    topology_path: Path, host: str = "0.0.0.0", port: int = 8002
) -> None:
    """
    Run the control API server.

    Args:
        topology_path: Path to network.yaml file
        host: Host to bind to
        port: Port to bind to
    """
    server = ControlAPIServer(topology_path)
    await server.start(host, port)
