"""Declarative video model capability registry.

Ported from DolphinToonFlow's modelList.ts — defines every supported video
model's capabilities (duration, resolution, aspect-ratio, generation type,
audio support) in a single source of truth.

Usage:
    from app.services.video_registry import VIDEO_REGISTRY
    caps = VIDEO_REGISTRY.get_capabilities("doubao-seedance-1-5-pro-251215")
    models = VIDEO_REGISTRY.list_models(manufacturer="volcengine")
    VIDEO_REGISTRY.validate("doubao-seedance-1-5-pro-251215", duration=8, resolution="720p")
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------

# Generation type taxonomy (matches Toonflow's VideoGenerationType)
GEN_TYPE_TEXT = "text"                    # Text-to-video
GEN_TYPE_SINGLE_IMAGE = "single_image"   # Single image-to-video
GEN_TYPE_START_END = "start_end"         # First + last frame required
GEN_TYPE_END_OPTIONAL = "end_optional"   # First frame + optional last frame
GEN_TYPE_START_OPTIONAL = "start_optional"
GEN_TYPE_MULTI_IMAGE = "multi_image"     # Multiple images
GEN_TYPE_REFERENCE = "reference"         # Reference image mode


@dataclass(frozen=True)
class DurationResolutionMap:
    """Allowed duration × resolution combination for a model."""
    durations: tuple[int, ...]
    resolutions: tuple[str, ...]


@dataclass(frozen=True)
class VideoModelCapability:
    """Capability descriptor for a single video model."""
    manufacturer: str
    model: str
    gen_types: tuple[str, ...]
    duration_resolution_map: tuple[DurationResolutionMap, ...]
    aspect_ratios: tuple[str, ...] = ()
    audio: bool = False


# ---------------------------------------------------------------------------
# Registry class
# ---------------------------------------------------------------------------

class VideoModelRegistry:
    """In-memory registry of all supported video models."""

    def __init__(self) -> None:
        self._models: dict[str, list[VideoModelCapability]] = {}
        self._by_manufacturer: dict[str, list[VideoModelCapability]] = {}

    def register(self, cap: VideoModelCapability) -> None:
        self._models.setdefault(cap.model, []).append(cap)
        self._by_manufacturer.setdefault(cap.manufacturer, []).append(cap)

    def get_capabilities(self, model: str) -> list[VideoModelCapability]:
        """Return all capability entries for a model (may have multiple for t2v vs i2v)."""
        return self._models.get(model, [])

    def list_models(self, manufacturer: str | None = None) -> list[VideoModelCapability]:
        """List models, optionally filtered by manufacturer."""
        if manufacturer:
            return self._by_manufacturer.get(manufacturer, [])
        return [cap for caps in self._models.values() for cap in caps]

    def list_manufacturers(self) -> list[str]:
        """Return sorted list of unique manufacturer names."""
        return sorted(self._by_manufacturer.keys())

    def validate(
        self,
        model: str,
        *,
        duration: int | None = None,
        resolution: str | None = None,
        aspect_ratio: str | None = None,
        gen_type: str | None = None,
        num_images: int = 0,
    ) -> VideoModelCapability:
        """Validate generation parameters against model capabilities.

        Returns the matching capability entry or raises ValueError.
        """
        caps = self.get_capabilities(model)
        if not caps:
            raise ValueError(f"Unknown video model: {model}")

        # Filter by gen_type if specified
        if gen_type:
            caps = [c for c in caps if gen_type in c.gen_types]
            if not caps:
                raise ValueError(
                    f"Model {model} does not support generation type '{gen_type}'"
                )

        # Infer gen_type from num_images if not explicit
        if not gen_type and num_images > 0:
            if num_images == 1:
                caps = [
                    c for c in caps
                    if any(t in c.gen_types for t in (
                        GEN_TYPE_SINGLE_IMAGE, GEN_TYPE_START_END,
                        GEN_TYPE_END_OPTIONAL, GEN_TYPE_REFERENCE,
                    ))
                ]
            elif num_images == 2:
                caps = [
                    c for c in caps
                    if any(t in c.gen_types for t in (
                        GEN_TYPE_START_END, GEN_TYPE_END_OPTIONAL,
                        GEN_TYPE_START_OPTIONAL,
                    ))
                ]
            elif num_images > 2:
                caps = [c for c in caps if GEN_TYPE_MULTI_IMAGE in c.gen_types]
            if not caps:
                raise ValueError(
                    f"Model {model} does not support {num_images}-image mode"
                )
        elif not gen_type and num_images == 0:
            # Text mode
            text_caps = [c for c in caps if GEN_TYPE_TEXT in c.gen_types]
            if text_caps:
                caps = text_caps

        # Validate duration + resolution
        if duration is not None or resolution is not None:
            valid = []
            for c in caps:
                for drm in c.duration_resolution_map:
                    dur_ok = duration is None or duration in drm.durations
                    res_ok = (
                        resolution is None
                        or len(drm.resolutions) == 0
                        or resolution in drm.resolutions
                    )
                    if dur_ok and res_ok:
                        valid.append(c)
                        break
            if not valid:
                raise ValueError(
                    f"Model {model} does not support "
                    f"duration={duration}, resolution={resolution}"
                )
            caps = valid

        # Validate aspect_ratio
        if aspect_ratio:
            valid = [
                c for c in caps
                if not c.aspect_ratios or aspect_ratio in c.aspect_ratios
            ]
            if not valid:
                raise ValueError(
                    f"Model {model} does not support aspect_ratio={aspect_ratio}"
                )
            caps = valid

        return caps[0]

    def to_dict_list(self) -> list[dict[str, Any]]:
        """Serialize all models for API response."""
        result = []
        for caps in self._models.values():
            for cap in caps:
                result.append({
                    "manufacturer": cap.manufacturer,
                    "model": cap.model,
                    "gen_types": list(cap.gen_types),
                    "duration_resolution_map": [
                        {
                            "durations": list(drm.durations),
                            "resolutions": list(drm.resolutions),
                        }
                        for drm in cap.duration_resolution_map
                    ],
                    "aspect_ratios": list(cap.aspect_ratios),
                    "audio": cap.audio,
                })
        return result


# ---------------------------------------------------------------------------
# Helper to reduce boilerplate
# ---------------------------------------------------------------------------

def _cap(
    mfr: str,
    model: str,
    types: list[str],
    durations: list[int],
    resolutions: list[str],
    aspect_ratios: list[str] | None = None,
    audio: bool = False,
    drm_list: list[dict] | None = None,
) -> VideoModelCapability:
    """Shorthand factory for VideoModelCapability."""
    if drm_list:
        drm = tuple(
            DurationResolutionMap(
                durations=tuple(d["durations"]),
                resolutions=tuple(d["resolutions"]),
            )
            for d in drm_list
        )
    else:
        drm = (DurationResolutionMap(
            durations=tuple(durations),
            resolutions=tuple(resolutions),
        ),)
    return VideoModelCapability(
        manufacturer=mfr,
        model=model,
        gen_types=tuple(types),
        duration_resolution_map=drm,
        aspect_ratios=tuple(aspect_ratios or []),
        audio=audio,
    )


# ---------------------------------------------------------------------------
# Build the global registry — ported from Toonflow modelList.ts
# ---------------------------------------------------------------------------

VIDEO_REGISTRY = VideoModelRegistry()

# ================== 火山引擎 / 豆包系列 ==================

VIDEO_REGISTRY.register(_cap(
    "volcengine", "doubao-seedance-1-5-pro-251215",
    ["text", "end_optional"],
    list(range(4, 13)), ["480p", "720p", "1080p"],
    ["16:9", "4:3", "1:1", "3:4", "9:16", "21:9"], audio=True,
))

VIDEO_REGISTRY.register(_cap(
    "volcengine", "doubao-seedance-1-0-pro-250528",
    ["text", "end_optional"],
    list(range(2, 13)), ["480p", "720p", "1080p"],
    ["16:9", "4:3", "1:1", "3:4", "9:16", "21:9"],
))

VIDEO_REGISTRY.register(_cap(
    "volcengine", "doubao-seedance-1-0-pro-fast-251015",
    ["text", "single_image"],
    list(range(2, 13)), ["480p", "720p", "1080p"],
    ["16:9", "4:3", "1:1", "3:4", "9:16", "21:9"],
))

VIDEO_REGISTRY.register(_cap(
    "volcengine", "doubao-seedance-1-0-lite-i2v-250428",
    ["end_optional", "reference"],
    list(range(2, 13)), ["480p", "720p", "1080p"],
))

VIDEO_REGISTRY.register(_cap(
    "volcengine", "doubao-seedance-1-0-lite-t2v-250428",
    ["text"],
    list(range(2, 13)), ["480p", "720p", "1080p"],
    ["16:9", "4:3", "1:1", "3:4", "9:16", "21:9"],
))

# ================== 可灵系列 ==================

for _model, _res, _modes in [
    ("kling-v1(STD)", ["720p"], []),
    ("kling-v1(PRO)", ["1080p"], []),
    ("kling-v1-6(PRO)", ["1080p"], []),
    ("kling-v2-5-turbo(PRO)", ["1080p"], []),
    ("kling-v2-6(PRO)", ["1080p"], []),
]:
    # text-to-video
    VIDEO_REGISTRY.register(_cap(
        "kling", _model, ["text"],
        [5, 10], _res,
        ["16:9", "1:1", "9:16"],
    ))
    # image-to-video
    VIDEO_REGISTRY.register(_cap(
        "kling", _model, ["start_end"],
        [5, 10], _res,
    ))

# ================== Vidu 系列 ==================

# viduq3-pro
VIDEO_REGISTRY.register(_cap(
    "vidu", "viduq3-pro", ["text"],
    list(range(1, 17)), ["540p", "720p", "1080p"],
    ["16:9", "9:16", "3:4", "4:3", "1:1"], audio=True,
))
VIDEO_REGISTRY.register(_cap(
    "vidu", "viduq3-pro", ["single_image"],
    list(range(1, 17)), ["540p", "720p", "1080p"],
    audio=True,
))

# viduq2-pro-fast
VIDEO_REGISTRY.register(_cap(
    "vidu", "viduq2-pro-fast", ["single_image", "start_end"],
    list(range(1, 11)), ["720p", "1080p"],
))

# viduq2-pro
VIDEO_REGISTRY.register(_cap(
    "vidu", "viduq2-pro", ["text"],
    list(range(1, 11)), ["540p", "720p", "1080p"],
    ["16:9", "9:16", "3:4", "4:3", "1:1"],
))
VIDEO_REGISTRY.register(_cap(
    "vidu", "viduq2-pro", ["single_image", "reference", "start_end"],
    list(range(1, 11)), ["540p", "720p", "1080p"],
))

# viduq2-turbo
VIDEO_REGISTRY.register(_cap(
    "vidu", "viduq2-turbo", ["text"],
    list(range(1, 11)), ["540p", "720p", "1080p"],
    ["16:9", "9:16", "3:4", "4:3", "1:1"],
))
VIDEO_REGISTRY.register(_cap(
    "vidu", "viduq2-turbo", ["single_image", "reference", "start_end"],
    list(range(1, 11)), ["540p", "720p", "1080p"],
))

# viduq1
VIDEO_REGISTRY.register(_cap(
    "vidu", "viduq1", ["text"],
    [5], ["1080p"],
    ["16:9", "9:16", "1:1"],
))
VIDEO_REGISTRY.register(_cap(
    "vidu", "viduq1", ["single_image", "reference", "start_end"],
    [5], ["1080p"],
))

# viduq1-classic
VIDEO_REGISTRY.register(_cap(
    "vidu", "viduq1-classic", ["single_image", "start_end"],
    [5], ["1080p"],
))

# vidu2.0
VIDEO_REGISTRY.register(_cap(
    "vidu", "vidu2.0", ["single_image", "reference", "start_end"],
    [], [],
    drm_list=[
        {"durations": [4], "resolutions": ["360p", "720p", "1080p"]},
        {"durations": [8], "resolutions": ["720p"]},
    ],
))

# ================== 万象 / DashScope 系列 ==================

# wan2.6-t2v
VIDEO_REGISTRY.register(_cap(
    "wan", "wan2.6-t2v",
    ["text"],
    list(range(2, 16)), ["720p", "1080p"],
    ["16:9", "9:16", "1:1", "4:3", "3:4"], audio=True,
))

# wan2.5-t2v-preview
VIDEO_REGISTRY.register(_cap(
    "wan", "wan2.5-t2v-preview",
    ["text"],
    [5, 10], ["480p", "720p", "1080p"],
    ["16:9", "9:16", "1:1", "4:3", "3:4"], audio=True,
))

# wan2.2-t2v-plus
VIDEO_REGISTRY.register(_cap(
    "wan", "wan2.2-t2v-plus",
    ["text"],
    [5], ["480p", "1080p"],
    ["16:9", "9:16", "1:1", "4:3", "3:4"],
))

# wanx2.1-t2v-turbo
VIDEO_REGISTRY.register(_cap(
    "wan", "wanx2.1-t2v-turbo",
    ["text"],
    [5], ["480p", "720p"],
    ["16:9", "9:16", "1:1", "4:3", "3:4"],
))

# wanx2.1-t2v-plus
VIDEO_REGISTRY.register(_cap(
    "wan", "wanx2.1-t2v-plus",
    ["text"],
    [5], ["720p"],
    ["16:9", "9:16", "1:1", "4:3", "3:4"],
))

# wan2.6-i2v-flash
VIDEO_REGISTRY.register(_cap(
    "wan", "wan2.6-i2v-flash",
    ["single_image"],
    list(range(2, 16)), ["720p", "1080p"],
    audio=True,
))

# wan2.6-i2v
VIDEO_REGISTRY.register(_cap(
    "wan", "wan2.6-i2v",
    ["single_image"],
    list(range(2, 16)), ["720p", "1080p"],
    audio=True,
))

# wan2.5-i2v-preview
VIDEO_REGISTRY.register(_cap(
    "wan", "wan2.5-i2v-preview",
    ["single_image"],
    [5, 10], ["480p", "720p", "1080p"],
    audio=True,
))

# wan2.2-i2v-flash
VIDEO_REGISTRY.register(_cap(
    "wan", "wan2.2-i2v-flash",
    ["single_image"],
    [5], ["480p", "720p", "1080p"],
))

# wan2.2-i2v-plus
VIDEO_REGISTRY.register(_cap(
    "wan", "wan2.2-i2v-plus",
    ["single_image"],
    [5], ["480p", "1080p"],
))

# wanx2.1-i2v-plus
VIDEO_REGISTRY.register(_cap(
    "wan", "wanx2.1-i2v-plus",
    ["single_image"],
    [5], ["720p"],
))

# wanx2.1-i2v-turbo
VIDEO_REGISTRY.register(_cap(
    "wan", "wanx2.1-i2v-turbo",
    ["single_image"],
    [3, 4, 5], ["480p", "720p"],
))

# wan2.2-kf2v-flash
VIDEO_REGISTRY.register(_cap(
    "wan", "wan2.2-kf2v-flash",
    ["start_end"],
    [5], ["480p", "720p", "1080p"],
))

# wanx2.1-kf2v-plus
VIDEO_REGISTRY.register(_cap(
    "wan", "wanx2.1-kf2v-plus",
    ["start_end"],
    [5], ["720p"],
))

# ================== Gemini Veo 系列 ==================

VIDEO_REGISTRY.register(_cap(
    "gemini", "veo-3.1-generate-preview",
    ["text", "single_image", "start_end", "end_optional", "reference"],
    [], [],
    ["16:9", "9:16"], audio=True,
    drm_list=[
        {"durations": [4, 6], "resolutions": ["720p"]},
        {"durations": [8], "resolutions": ["720p", "1080p"]},
    ],
))

VIDEO_REGISTRY.register(_cap(
    "gemini", "veo-3.1-fast-generate-preview",
    ["text", "single_image", "start_end", "end_optional", "reference"],
    [], [],
    ["16:9", "9:16"], audio=True,
    drm_list=[
        {"durations": [4, 6], "resolutions": ["720p"]},
        {"durations": [8], "resolutions": ["720p", "1080p"]},
    ],
))

VIDEO_REGISTRY.register(_cap(
    "gemini", "veo-3.0-generate-preview",
    ["text", "single_image"],
    [], [],
    ["16:9", "9:16"], audio=True,
    drm_list=[
        {"durations": [4, 6], "resolutions": ["720p"]},
        {"durations": [8], "resolutions": ["720p", "1080p"]},
    ],
))

VIDEO_REGISTRY.register(_cap(
    "gemini", "veo-3.0-fast-generate-preview",
    ["text", "single_image"],
    [], [],
    ["16:9", "9:16"], audio=True,
    drm_list=[
        {"durations": [4, 6], "resolutions": ["720p"]},
        {"durations": [8], "resolutions": ["720p", "1080p"]},
    ],
))

VIDEO_REGISTRY.register(_cap(
    "gemini", "veo-2.0-generate-001",
    ["text", "single_image"],
    [5, 6, 7, 8], ["720p"],
    ["16:9", "9:16"],
))

# ================== Sora / RunningHub 系列 ==================

VIDEO_REGISTRY.register(_cap(
    "runninghub", "sora-2",
    ["single_image", "text"],
    [10, 15], [],
    ["16:9", "9:16"],
))

VIDEO_REGISTRY.register(_cap(
    "runninghub", "sora-2-pro",
    ["single_image", "text"],
    [15, 25], [],
    ["16:9", "9:16"],
))

# ================== Apimart 系列 ==================

VIDEO_REGISTRY.register(_cap(
    "apimart", "sora-2",
    ["single_image", "text"],
    [10, 15], [],
    ["16:9", "9:16"],
))

VIDEO_REGISTRY.register(_cap(
    "apimart", "sora-2-pro",
    ["single_image", "text"],
    [15, 25], [],
    ["16:9", "9:16"],
))


logger.info(
    "Video registry initialized: %d models from %d manufacturers",
    len(VIDEO_REGISTRY._models),
    len(VIDEO_REGISTRY._by_manufacturer),
)
