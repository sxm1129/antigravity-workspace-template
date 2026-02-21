"""Sora/RunningHub video generation provider.

Ported from DolphinToonFlow Toonflow-app/src/utils/ai/video/owned/runninghub.ts.

Supports: sora-2, sora-2-pro via RunningHub proxy API.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)


async def generate_video(
    *,
    prompt: str,
    model: str,
    api_key: str,
    base_url: str,
    image_base64: list[str] | None = None,
    duration: int = 10,
    aspect_ratio: str = "16:9",
    http_client: httpx.AsyncClient | None = None,
    poll_interval: int = 15,
    poll_timeout: int = 900,
) -> dict[str, Any]:
    """Generate video via RunningHub/Sora API.

    Returns dict with 'video_url' key on success.
    """
    if not api_key:
        raise ValueError("RunningHub/Sora API key is required")
    if not base_url:
        raise ValueError("RunningHub/Sora base URL is required")

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    # Build request
    body: dict[str, Any] = {
        "model": model,
        "prompt": prompt,
        "duration": duration,
        "aspect_ratio": aspect_ratio,
    }

    # Upload image first if provided
    if image_base64 and len(image_base64) > 0:
        image_url = await _upload_image(
            image_base64[0], api_key, base_url, http_client
        )
        body["image_url"] = image_url

    client = http_client or httpx.AsyncClient(timeout=60.0)
    own_client = http_client is None

    try:
        # Create generation task
        create_url = f"{base_url}/api/v1/video/generate"
        resp = await client.post(create_url, json=body, headers=headers)
        resp.raise_for_status()
        result = resp.json()

        task_id = result.get("task_id") or result.get("id")
        if not task_id:
            raise RuntimeError(f"Sora task creation failed: {result}")

        logger.info("Sora task created: %s (model=%s)", task_id, model)

        # Poll for completion
        poll_url = f"{base_url}/api/v1/video/status/{task_id}"
        elapsed = 0

        while elapsed < poll_timeout:
            await asyncio.sleep(poll_interval)
            elapsed += poll_interval

            poll_resp = await client.get(poll_url, headers=headers)
            poll_resp.raise_for_status()
            poll_data = poll_resp.json()

            status = poll_data.get("status", "").lower()

            if status in ("completed", "succeeded", "success"):
                video_url = poll_data.get("video_url") or poll_data.get("url")
                if not video_url:
                    raise RuntimeError("Sora task succeeded but no video URL")
                return {"video_url": video_url, "task_id": task_id}

            elif status in ("failed", "error"):
                msg = poll_data.get("error", "unknown")
                raise RuntimeError(f"Sora task failed: {msg}")

            elif status in ("pending", "processing", "queued", "running"):
                logger.debug("Sora task %s: %s", task_id, status)
                continue

            else:
                logger.warning("Sora unknown status: %s", status)

        raise RuntimeError(f"Sora task timed out after {poll_timeout}s")
    finally:
        if own_client:
            await client.aclose()


async def _upload_image(
    image_base64: str,
    api_key: str,
    base_url: str,
    http_client: httpx.AsyncClient | None = None,
) -> str:
    """Upload base64 image to RunningHub, return URL."""
    import base64 as b64_mod
    import re

    # Strip data URL prefix
    b64_data = re.sub(r"^data:image/[^;]+;base64,", "", image_base64)
    image_bytes = b64_mod.b64decode(b64_data)

    upload_url = f"{base_url}/api/v1/upload"
    headers = {
        "Authorization": f"Bearer {api_key}",
    }

    client = http_client or httpx.AsyncClient(timeout=30.0)
    own_client = http_client is None

    try:
        files = {"file": ("image.png", image_bytes, "image/png")}
        resp = await client.post(upload_url, headers=headers, files=files)
        resp.raise_for_status()
        result = resp.json()
        return result.get("url", "")
    finally:
        if own_client:
            await client.aclose()
