"""
Scene builder for loading and configuring ray tracing scenes.

Handles loading the default two-room scene or custom Mitsuba XML scenes,
and configuring them for Sionna ray tracing.
"""

import logging
from pathlib import Path
from typing import Optional, Union

logger = logging.getLogger(__name__)

# Path to default scene (relative to package)
DEFAULT_SCENE_NAME = "two_room_default.xml"


def get_default_scene_path() -> Path:
    """
    Get path to the default two-room scene.

    Returns:
        Path to two_room_default.xml
    """
    # Try to find scenes directory relative to this file
    module_dir = Path(__file__).parent.parent.parent.parent  # src/sine/scene -> project root
    scenes_dir = module_dir / "scenes"

    default_scene = scenes_dir / DEFAULT_SCENE_NAME

    if default_scene.exists():
        return default_scene

    # Try alternative locations
    alt_paths = [
        Path("/home/joshua/Documents/SiNE/scenes") / DEFAULT_SCENE_NAME,
        Path.cwd() / "scenes" / DEFAULT_SCENE_NAME,
    ]

    for alt_path in alt_paths:
        if alt_path.exists():
            return alt_path

    raise FileNotFoundError(
        f"Default scene not found. Searched:\n"
        f"  - {default_scene}\n"
        f"  - {alt_paths}"
    )


class SceneBuilder:
    """
    Build and configure scenes for Sionna ray tracing.

    Handles loading scene files and preparing them for channel computation.
    """

    def __init__(self):
        """Initialize scene builder."""
        self._scene_path: Optional[Path] = None
        self._scene_type: str = "default"

    def load_default_scene(self) -> Path:
        """
        Load the default two-room scene.

        Returns:
            Path to the default scene file
        """
        self._scene_path = get_default_scene_path()
        self._scene_type = "default"
        logger.info(f"Loaded default scene: {self._scene_path}")
        return self._scene_path

    def load_custom_scene(self, scene_path: Union[str, Path]) -> Path:
        """
        Load a custom Mitsuba XML scene.

        Args:
            scene_path: Path to the Mitsuba XML scene file

        Returns:
            Path to the scene file

        Raises:
            FileNotFoundError: If scene file doesn't exist
            ValueError: If file is not a valid XML file
        """
        path = Path(scene_path)

        if not path.exists():
            raise FileNotFoundError(f"Scene file not found: {scene_path}")

        if not path.suffix.lower() == ".xml":
            raise ValueError(f"Scene file must be XML format: {scene_path}")

        self._scene_path = path
        self._scene_type = "custom"
        logger.info(f"Loaded custom scene: {self._scene_path}")
        return self._scene_path

    def load_from_config(self, scene_config: dict) -> Optional[Path]:
        """
        Load scene based on configuration dictionary.

        Args:
            scene_config: Scene configuration with 'type' and optional 'file' keys

        Returns:
            Path to the scene file, or None if using empty scene
        """
        scene_type = scene_config.get("type", "default")

        if scene_type == "custom":
            custom_file = scene_config.get("file")
            if not custom_file:
                raise ValueError("Custom scene requires 'file' path")
            return self.load_custom_scene(custom_file)
        elif scene_type == "default":
            return self.load_default_scene()
        else:
            raise ValueError(f"Unknown scene type: {scene_type}")

    @property
    def scene_path(self) -> Optional[Path]:
        """Get current scene path."""
        return self._scene_path

    @property
    def scene_type(self) -> str:
        """Get current scene type ('default' or 'custom')."""
        return self._scene_type

    def validate_scene(self) -> list[str]:
        """
        Validate the loaded scene file.

        Returns:
            List of warnings/errors found in the scene
        """
        warnings = []

        if self._scene_path is None:
            warnings.append("No scene loaded")
            return warnings

        if not self._scene_path.exists():
            warnings.append(f"Scene file not found: {self._scene_path}")
            return warnings

        # Basic XML validation
        try:
            import xml.etree.ElementTree as ET

            tree = ET.parse(self._scene_path)
            root = tree.getroot()

            # Check for scene element
            if root.tag != "scene":
                warnings.append(f"Root element is '{root.tag}', expected 'scene'")

            # Check for shapes
            shapes = root.findall(".//shape")
            if not shapes:
                warnings.append("No geometry shapes found in scene")

            # Check for materials/BSDFs
            bsdfs = root.findall(".//bsdf")
            if not bsdfs:
                warnings.append("No materials (BSDFs) defined in scene")

        except ET.ParseError as e:
            warnings.append(f"XML parse error: {e}")
        except Exception as e:
            warnings.append(f"Validation error: {e}")

        return warnings


def get_scene_info(scene_path: Union[str, Path]) -> dict:
    """
    Get information about a scene file.

    Args:
        scene_path: Path to scene file

    Returns:
        Dictionary with scene information
    """
    path = Path(scene_path)

    info = {
        "path": str(path),
        "exists": path.exists(),
        "size_bytes": path.stat().st_size if path.exists() else 0,
        "shapes": [],
        "materials": [],
        "lights": [],
    }

    if path.exists():
        try:
            import xml.etree.ElementTree as ET

            tree = ET.parse(path)
            root = tree.getroot()

            # Count shapes
            for shape in root.findall(".//shape"):
                shape_type = shape.get("type", "unknown")
                shape_id = shape.get("id", "unnamed")
                info["shapes"].append({"type": shape_type, "id": shape_id})

            # Count materials
            for bsdf in root.findall(".//bsdf"):
                bsdf_type = bsdf.get("type", "unknown")
                bsdf_id = bsdf.get("id", "unnamed")
                info["materials"].append({"type": bsdf_type, "id": bsdf_id})

            # Count lights
            for emitter in root.findall(".//emitter"):
                emitter_type = emitter.get("type", "unknown")
                emitter_id = emitter.get("id", "unnamed")
                info["lights"].append({"type": emitter_type, "id": emitter_id})

        except Exception as e:
            info["error"] = str(e)

    return info
