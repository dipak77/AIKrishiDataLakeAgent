"""Vision subpackage (V5-C): pluggable image diagnosis inference."""

from vision.inference import (  # noqa: F401
    BackendUnavailable,
    Image,
    VisionCandidate,
    VisionError,
    VisionResult,
    analyze_image,
    decode_png,
    get_backend,
)

__all__ = [
    "analyze_image",
    "decode_png",
    "get_backend",
    "Image",
    "VisionCandidate",
    "VisionResult",
    "VisionError",
    "BackendUnavailable",
]
