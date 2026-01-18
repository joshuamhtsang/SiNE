"""
Emulation API Server for SiNE.

Provides REST API endpoints for monitoring and controlling emulation state.
This API exposes the EmulationController's deployment summary and state information.

Example usage:
    # Query deployment summary
    curl http://localhost:8001/api/emulation/summary

    # Check emulation health
    curl http://localhost:8001/health
"""

import logging
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException

from sine.emulation.controller import EmulationController

logger = logging.getLogger(__name__)


class EmulationAPIServer:
    """
    REST API server for emulation monitoring and control.

    Wraps an EmulationController and exposes endpoints for querying
    deployment state, link parameters, and channel metrics.
    """

    def __init__(self, controller: EmulationController):
        """
        Initialize emulation API server.

        Args:
            controller: Emulation controller instance
        """
        self.controller = controller
        self.app = FastAPI(
            title="SiNE Emulation API",
            description="Monitor and control wireless network emulation state",
            version="0.1.0",
        )

        # Register routes
        self._register_routes()

    def _register_routes(self) -> None:
        """Register API routes."""

        @self.app.get("/health")
        async def health():
            """Health check endpoint."""
            if self.controller and self.controller.is_running:
                return {
                    "status": "healthy",
                    "emulation": "running",
                    "topology": self.controller.config.name if self.controller.config else "unknown",
                }
            return {
                "status": "degraded",
                "emulation": "not running",
                "message": "Emulation not started or has stopped",
            }

        @self.app.get("/api/emulation/summary")
        async def get_deployment_summary():
            """
            Get deployment summary including containers, links, and channel parameters.

            Returns detailed information about:
            - Deployed containers (name, image, PID, interfaces, positions, IPs)
            - Link parameters (netem params, RF metrics, MCS info)
            - SNR/SINR values when MAC model is present
            - MAC model type (csma, tdma, or None)
            - MCS selection info (modulation, code rate, FEC type, bandwidth)

            This endpoint is useful for:
            - Integration testing (verify SINR-based MCS selection)
            - Monitoring deployed emulations
            - Debugging channel computation
            - Validating netem configuration

            Example response for a link with CSMA MAC model:
            ```json
            {
                "topology_name": "csma-mcs-test",
                "mode": "shared_bridge",
                "containers": [...],
                "links": [
                    {
                        "link": "node1 (eth1) <-> node2 (eth1)",
                        "type": "wireless",
                        "tx_node": "node1",
                        "rx_node": "node2",
                        "tx_interface": "eth1",
                        "rx_interface": "eth1",
                        "delay_ms": 0.067,
                        "jitter_ms": 0.0,
                        "loss_percent": 0.0,
                        "rate_mbps": 532.5,
                        "snr_db": 48.2,
                        "sinr_db": 45.1,
                        "mac_model_type": "csma",
                        "path_loss_db": 66.3,
                        "per": 0.0,
                        "rx_power_dbm": -46.3,
                        "mcs_index": 11,
                        "modulation": "1024qam",
                        "code_rate": 0.833,
                        "fec_type": "ldpc",
                        "bandwidth_mhz": 80.0
                    }
                ]
            }
            ```
            """
            if not self.controller or not self.controller.is_running:
                raise HTTPException(status_code=503, detail="Emulation not running")

            return self.controller.get_deployment_summary()

        @self.app.get("/api/emulation/links")
        async def get_links():
            """
            Get just the links from the deployment summary.

            Convenient endpoint for querying link parameters without
            the full container information.
            """
            if not self.controller or not self.controller.is_running:
                raise HTTPException(status_code=503, detail="Emulation not running")

            summary = self.controller.get_deployment_summary()
            return {"links": summary.get("links", [])}

        @self.app.get("/api/emulation/links/{tx_node}/{rx_node}")
        async def get_link(tx_node: str, rx_node: str):
            """
            Get parameters for a specific link.

            Args:
                tx_node: Transmitter node name
                rx_node: Receiver node name

            Returns:
                Link parameters including netem, RF metrics, and MCS info
            """
            if not self.controller or not self.controller.is_running:
                raise HTTPException(status_code=503, detail="Emulation not running")

            summary = self.controller.get_deployment_summary()
            for link in summary.get("links", []):
                if link["tx_node"] == tx_node and link["rx_node"] == rx_node:
                    return link

            raise HTTPException(
                status_code=404,
                detail=f"Link {tx_node} -> {rx_node} not found"
            )
