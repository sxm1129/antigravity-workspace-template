"""Model management API — list supported models and test connectivity."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException

from app.services.video_registry import VIDEO_REGISTRY
from app.services.image_registry import IMAGE_REGISTRY

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/models", tags=["models"])


@router.get("/video")
async def list_video_models(manufacturer: str | None = None) -> dict[str, Any]:
    """List all supported video models with their capabilities."""
    if manufacturer:
        models = VIDEO_REGISTRY.list_models(manufacturer=manufacturer)
    else:
        models = VIDEO_REGISTRY.list_models()

    return {
        "models": VIDEO_REGISTRY.to_dict_list() if not manufacturer else [
            {
                "manufacturer": m.manufacturer,
                "model": m.model,
                "gen_types": list(m.gen_types),
                "duration_resolution_map": [
                    {"durations": list(d.durations), "resolutions": list(d.resolutions)}
                    for d in m.duration_resolution_map
                ],
                "aspect_ratios": list(m.aspect_ratios),
                "audio": m.audio,
            }
            for m in models
        ],
        "manufacturers": VIDEO_REGISTRY.list_manufacturers(),
        "total": len(models) if manufacturer else len(VIDEO_REGISTRY._models),
    }


@router.get("/image")
async def list_image_models(manufacturer: str | None = None) -> dict[str, Any]:
    """List all supported image models with their capabilities."""
    if manufacturer:
        models = IMAGE_REGISTRY.list_models(manufacturer=manufacturer)
    else:
        models = IMAGE_REGISTRY.list_models()

    return {
        "models": IMAGE_REGISTRY.to_dict_list() if not manufacturer else [
            {
                "manufacturer": m.manufacturer,
                "model": m.model,
                "gen_type": m.gen_type,
                "grid": m.grid,
            }
            for m in models
        ],
        "manufacturers": IMAGE_REGISTRY.list_manufacturers(),
        "total": len(models),
    }


@router.get("/video/validate")
async def validate_video_config(
    model: str,
    duration: int | None = None,
    resolution: str | None = None,
    aspect_ratio: str | None = None,
    gen_type: str | None = None,
    num_images: int = 0,
) -> dict[str, Any]:
    """Validate video generation parameters against model capabilities."""
    try:
        cap = VIDEO_REGISTRY.validate(
            model,
            duration=duration,
            resolution=resolution,
            aspect_ratio=aspect_ratio,
            gen_type=gen_type,
            num_images=num_images,
        )
        return {
            "valid": True,
            "matched_capability": {
                "manufacturer": cap.manufacturer,
                "model": cap.model,
                "gen_types": list(cap.gen_types),
                "audio": cap.audio,
            },
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/test")
async def test_model_connectivity(
    manufacturer: str,
    api_key: str,
    base_url: str | None = None,
) -> dict[str, Any]:
    """Test connectivity to a model provider (lightweight health check)."""
    import httpx

    test_urls: dict[str, str] = {
        "volcengine": "https://ark.cn-beijing.volces.com/api/v3/models",
        "kling": "https://api-beijing.klingai.com/v1/models",
        "vidu": "https://api.vidu.cn/ent/v2/tasks",
        "wan": "https://dashscope.aliyuncs.com/api/v1/models",
        "gemini": "https://generativelanguage.googleapis.com/v1beta/models",
        "runninghub": f"{base_url or 'https://api.runninghub.com'}/api/v1/models",
    }

    url = test_urls.get(manufacturer)
    if not url:
        return {"connected": False, "error": f"Unknown manufacturer: {manufacturer}"}

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            if manufacturer == "gemini":
                resp = await client.get(f"{url}?key={api_key}")
            else:
                headers = {"Authorization": f"Bearer {api_key}"}
                if manufacturer == "vidu":
                    headers["Authorization"] = f"Token {api_key}"
                resp = await client.get(url, headers=headers)

            return {
                "connected": resp.status_code < 500,
                "status_code": resp.status_code,
                "manufacturer": manufacturer,
            }
    except Exception as e:
        return {
            "connected": False,
            "error": str(e),
            "manufacturer": manufacturer,
        }
