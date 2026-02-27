"""
EngineRegistry: manages channel engine lifecycle.

Encapsulates the three engine-related globals and `get_engine_for_request()`
that were previously in server.py.
"""

import logging

from fastapi import HTTPException

from sine.channel.sionna_engine import ChannelEngine, is_sionna_available

logger = logging.getLogger(__name__)


class EngineRegistry:
    """
    Manages SionnaEngine and FallbackEngine instances.

    Replaces the _engine, _fallback_engine, and _force_fallback_mode globals
    in server.py, and the get_engine_for_request() function.
    """

    def __init__(self) -> None:
        self._engine: ChannelEngine | None = None
        self._fallback_engine: ChannelEngine | None = None
        self._force_fallback: bool = False

    def configure(self, force_fallback: bool) -> None:
        """Set server-wide force-fallback mode (CLI --force-fallback flag)."""
        self._force_fallback = force_fallback

    def get(self, engine_type_str: str) -> ChannelEngine:
        """
        Return the appropriate engine for the requested type string.

        Args:
            engine_type_str: "auto", "sionna", or "fallback"

        Returns:
            Appropriate ChannelEngine instance

        Raises:
            HTTPException 400: If Sionna requested while server is in force-fallback mode
            HTTPException 503: If Sionna requested but unavailable
        """
        from sine.channel.sionna_engine import SionnaEngine, FallbackEngine

        # Check force-fallback mode first
        if self._force_fallback:
            if engine_type_str == "sionna":
                raise HTTPException(
                    status_code=400,
                    detail=(
                        "Server in fallback-only mode (started with --force-fallback). "
                        "Sionna engine not available."
                    ),
                )
            if self._fallback_engine is None:
                self._fallback_engine = FallbackEngine()
            return self._fallback_engine

        if engine_type_str == "auto":
            if self._engine is None:
                if is_sionna_available():
                    self._engine = SionnaEngine()
                else:
                    logger.warning("Sionna unavailable, using fallback FSPL engine")
                    self._engine = FallbackEngine()
            return self._engine

        if engine_type_str == "sionna":
            if not is_sionna_available():
                raise HTTPException(
                    status_code=503,
                    detail="Sionna engine requested but unavailable (GPU/CUDA required)",
                )
            if self._engine is None or self._engine.engine_type != "sionna":
                self._engine = SionnaEngine()
            return self._engine

        if engine_type_str == "fallback":
            if self._fallback_engine is None:
                self._fallback_engine = FallbackEngine()
            return self._fallback_engine

        raise ValueError(f"Unknown engine_type: {engine_type_str}")

    @property
    def primary_engine(self) -> ChannelEngine | None:
        """Return the current primary (auto/sionna) engine instance, or None."""
        return self._engine
