"""Declarative image model capability registry.

Ported from DolphinToonFlow's image/modelList.ts.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


# Image generation type taxonomy
GEN_TYPE_T2I = "t2i"      # Text-to-image
GEN_TYPE_TI2I = "ti2i"    # Text + image to image
GEN_TYPE_I2I = "i2i"      # Image-to-image


@dataclass(frozen=True)
class ImageModelCapability:
    """Capability descriptor for a single image model."""
    manufacturer: str
    model: str
    gen_type: str           # t2i, ti2i, i2i
    grid: bool = False      # Supports multi-panel grid generation


class ImageModelRegistry:
    """In-memory registry of all supported image models."""

    def __init__(self) -> None:
        self._models: dict[str, ImageModelCapability] = {}
        self._by_manufacturer: dict[str, list[ImageModelCapability]] = {}

    def register(self, cap: ImageModelCapability) -> None:
        self._models[f"{cap.manufacturer}:{cap.model}"] = cap
        self._by_manufacturer.setdefault(cap.manufacturer, []).append(cap)

    def get_capability(self, model: str, manufacturer: str | None = None) -> ImageModelCapability | None:
        if manufacturer:
            return self._models.get(f"{manufacturer}:{model}")
        # Search all manufacturers
        for key, cap in self._models.items():
            if cap.model == model:
                return cap
        return None

    def list_models(self, manufacturer: str | None = None) -> list[ImageModelCapability]:
        if manufacturer:
            return self._by_manufacturer.get(manufacturer, [])
        return list(self._models.values())

    def list_manufacturers(self) -> list[str]:
        return sorted(self._by_manufacturer.keys())

    def to_dict_list(self) -> list[dict[str, Any]]:
        return [
            {
                "manufacturer": cap.manufacturer,
                "model": cap.model,
                "gen_type": cap.gen_type,
                "grid": cap.grid,
            }
            for cap in self._models.values()
        ]


# ---------------------------------------------------------------------------
# Build the global registry
# ---------------------------------------------------------------------------

IMAGE_REGISTRY = ImageModelRegistry()

# 火山引擎
IMAGE_REGISTRY.register(ImageModelCapability("volcengine", "doubao-seedream-4-5-251128", GEN_TYPE_TI2I))
IMAGE_REGISTRY.register(ImageModelCapability("volcengine", "doubao-seedream-4-0-250828", GEN_TYPE_TI2I))

# 可灵
IMAGE_REGISTRY.register(ImageModelCapability("kling", "kling-image-o1", GEN_TYPE_TI2I))

# Gemini
IMAGE_REGISTRY.register(ImageModelCapability("gemini", "gemini-2.5-flash-image", GEN_TYPE_TI2I, grid=True))
IMAGE_REGISTRY.register(ImageModelCapability("gemini", "gemini-3-pro-image-preview", GEN_TYPE_TI2I, grid=True))

# Vidu
IMAGE_REGISTRY.register(ImageModelCapability("vidu", "viduq1", GEN_TYPE_I2I))
IMAGE_REGISTRY.register(ImageModelCapability("vidu", "viduq2", GEN_TYPE_TI2I))

# RunningHub
IMAGE_REGISTRY.register(ImageModelCapability("runninghub", "nanobanana", GEN_TYPE_TI2I, grid=True))

# Flux (existing MotionWeaver provider)
IMAGE_REGISTRY.register(ImageModelCapability("flux", "FLUX.1-schnell", GEN_TYPE_T2I))

# OpenRouter / Gemini (existing MotionWeaver provider via OpenRouter)
IMAGE_REGISTRY.register(ImageModelCapability("openrouter", "google/gemini-2.5-flash-image", GEN_TYPE_TI2I, grid=True))


logger.info(
    "Image registry initialized: %d models from %d manufacturers",
    len(IMAGE_REGISTRY._models),
    len(IMAGE_REGISTRY._by_manufacturer),
)
