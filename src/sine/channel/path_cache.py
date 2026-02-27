"""
PathCache: stores computed ray tracing paths for visualization.

Encapsulates the per-link path data and device positions that were previously
held in global dicts in server.py (_path_cache, _device_positions).
"""

import logging

from sine.channel.sionna_engine import PathResult, PathDetails

logger = logging.getLogger(__name__)


def _calculate_k_factor(path_details: PathDetails) -> float | None:
    """Calculate Rician K-factor (LOS/NLOS power ratio) in dB."""
    import numpy as np

    los_paths = [p for p in path_details.paths if p.is_los]
    nlos_paths = [p for p in path_details.paths if not p.is_los]

    if not los_paths:
        return None

    p_los = 10 ** (los_paths[0].power_db / 10)
    p_nlos_total = sum(10 ** (p.power_db / 10) for p in nlos_paths)

    if p_nlos_total < 1e-20:
        return 100.0

    k_linear = p_los / p_nlos_total
    return float(10 * np.log10(k_linear))


class PathCache:
    """
    Cache computed path data for visualization.

    Thread-safety: not required — the channel server is single-threaded
    (FastAPI with asyncio) and all mutations happen inside request handlers.
    """

    def __init__(self) -> None:
        self._links: dict[str, dict] = {}
        self._positions: dict[str, tuple[float, float, float]] = {}

    def store(
        self,
        tx_node: str,
        rx_node: str,
        tx_pos: tuple[float, float, float],
        rx_pos: tuple[float, float, float],
        path_result: PathResult,
        path_details: PathDetails,
        bandwidth_hz: float,
    ) -> None:
        """
        Cache computed path data for a link.

        Args:
            tx_node: Transmitter node name
            rx_node: Receiver node name
            tx_pos: Transmitter position (x, y, z)
            rx_pos: Receiver position (x, y, z)
            path_result: Ray tracing path computation results
            path_details: Detailed path information with vertices and interactions
            bandwidth_hz: Channel bandwidth in Hz
        """
        logger.info("Caching visualization data for link %s->%s", tx_node, rx_node)

        try:
            link_id = f"{tx_node}->{rx_node}"

            k_factor_db = _calculate_k_factor(path_details)

            if path_result.delay_spread_ns > 0:
                coherence_bw_hz = 1.0 / (5.0 * path_result.delay_spread_ns * 1e-9)
            else:
                coherence_bw_hz = bandwidth_hz

            sorted_paths = sorted(path_details.paths, key=lambda p: p.power_db, reverse=True)
            limited_paths = sorted_paths[:5]

            total_power_linear = sum(10 ** (p.power_db / 10) for p in path_details.paths)
            shown_power_linear = sum(10 ** (p.power_db / 10) for p in limited_paths)
            power_coverage_pct = (
                100 * shown_power_linear / total_power_linear if total_power_linear > 0 else 0
            )

            paths_data = [
                {
                    "delay_ns": float(p.delay_ns),
                    "power_db": float(p.power_db),
                    "vertices": [[float(v[0]), float(v[1]), float(v[2])] for v in p.vertices],
                    "interaction_types": p.interaction_types,
                    "is_los": p.is_los,
                    "doppler_hz": None,
                }
                for p in limited_paths
            ]

            self._links[link_id] = {
                "tx_name": tx_node,
                "rx_name": rx_node,
                "tx_position": [tx_pos[0], tx_pos[1], tx_pos[2]],
                "rx_position": [rx_pos[0], rx_pos[1], rx_pos[2]],
                "distance_m": float(path_details.distance_m),
                "num_paths_total": path_details.num_paths,
                "num_paths_shown": len(paths_data),
                "power_coverage_percent": float(power_coverage_pct),
                "rms_delay_spread_ns": float(path_result.delay_spread_ns),
                "coherence_bandwidth_hz": float(coherence_bw_hz),
                "k_factor_db": float(k_factor_db) if k_factor_db is not None else None,
                "dominant_path_type": path_result.dominant_path_type,
                "paths": paths_data,
            }

            self._positions[tx_node] = tx_pos
            self._positions[rx_node] = rx_pos

            logger.info(
                "Cached %d paths for link %s. Total cache size: %d",
                len(paths_data),
                link_id,
                len(self._links),
            )

        except Exception as e:
            logger.warning("Failed to cache paths for visualization: %s", e)
            import traceback
            logger.warning(traceback.format_exc())

    def get_state(self) -> dict:
        """Return the full visualization state (links and device positions)."""
        return {
            "links": dict(self._links),
            "positions": dict(self._positions),
        }

    @property
    def links(self) -> dict[str, dict]:
        return self._links

    @property
    def positions(self) -> dict[str, tuple[float, float, float]]:
        return self._positions
