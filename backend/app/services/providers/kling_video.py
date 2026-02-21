"""Kling video generation provider.

Ported from DolphinToonFlow Toonflow-app/src/utils/ai/video/owned/kling.ts.

Supports:
- kling-v1(STD/PRO), kling-v1-6(PRO), kling-v2-5-turbo(PRO), kling-v2-6(PRO)
- Text-to-video and image-to-video (first + last frame)
"""

from __future__ import annotations

import logging
import re
from typing import Any

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

# Default API endpoints
_DEFAULT_I2V_URL = "https://api-beijing.klingai.com/v1/videos/image2video"
_DEFAULT_T2V_URL = "https://api-beijing.klingai.com/v1/videos/text2video"
_DEFAULT_QUERY_URL = "https://api-beijing.klingai.com/v1/videos/text2video/{taskId}"


async def generate_video(
    *,
    prompt: str,
    model: str,
    api_key: str,
    base_url: str | None = None,
    image_base64: list[str] | None = None,
    duration: int = 5,
    aspect_ratio: str = "16:9",
    resolution: str | None = None,
    http_client: httpx.AsyncClient | None = None,
    poll_interval: int = 10,
    poll_timeout: int = 600,
) -> dict[str, Any]:
    """Generate video via Kling API.

    Returns dict with 'video_url' key on success.
    """
    if not api_key:
        raise ValueError("Kling API key is required")

    # Parse base_url: "i2v_url|t2v_url|query_url"
    if base_url:
        parts = base_url.split("|")
        i2v_url = parts[0] if len(parts) > 0 else _DEFAULT_I2V_URL
        t2v_url = parts[1] if len(parts) > 1 else _DEFAULT_T2V_URL
        query_url = parts[2] if len(parts) > 2 else _DEFAULT_QUERY_URL
    else:
        i2v_url, t2v_url, query_url = _DEFAULT_I2V_URL, _DEFAULT_T2V_URL, _DEFAULT_QUERY_URL

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    # Parse model name and mode: "kling-v2-6(PRO)" → model_name=kling-v2-6, mode=pro
    match = re.match(r"^(.+)\((STD|PRO)\)$", model, re.IGNORECASE)
    model_name = match.group(1) if match else model
    mode = match.group(2).lower() if match else "std"

    has_images = bool(image_base64 and len(image_base64) > 0)
    create_url = i2v_url if has_images else t2v_url

    body: dict[str, Any] = {
        "model_name": model_name,
        "mode": mode,
        "duration": str(duration),
        "prompt": prompt,
        "aspect_ratio": aspect_ratio,
    }

    if has_images:
        # Strip data URL prefix — Kling requires raw base64
        def strip_data_url(s: str) -> str:
            return re.sub(r"^data:image/[^;]+;base64,", "", s)

        body["image"] = strip_data_url(image_base64[0])
        if len(image_base64) > 1:
            body["image_tail"] = strip_data_url(image_base64[1])

    client = http_client or httpx.AsyncClient(timeout=30.0)
    own_client = http_client is None

    try:
        # Create task
        resp = await client.post(create_url, json=body, headers=headers)
        resp.raise_for_status()
        create_data = resp.json()

        if create_data.get("code") != 0:
            raise RuntimeError(
                f"Kling task creation failed: {create_data.get('message', 'unknown error')}"
            )

        task_id = create_data.get("data", {}).get("task_id")
        if not task_id:
            raise RuntimeError("Kling task creation failed: no task_id returned")

        logger.info("Kling task created: %s (model=%s)", task_id, model)

        # Poll for completion
        import asyncio
        elapsed = 0
        while elapsed < poll_timeout:
            await asyncio.sleep(poll_interval)
            elapsed += poll_interval

            poll_url = query_url.replace("{taskId}", task_id)
            poll_resp = await client.get(poll_url, headers=headers)
            poll_resp.raise_for_status()
            poll_data = poll_resp.json()

            if poll_data.get("code") != 0:
                logger.warning("Kling poll error: %s", poll_data.get("message"))
                continue

            task = poll_data.get("data", {})
            status = task.get("task_status")

            if status == "succeed":
                video_url = (
                    task.get("task_result", {})
                    .get("videos", [{}])[0]
                    .get("url")
                )
                if not video_url:
                    raise RuntimeError("Kling task succeeded but no video URL")
                return {"video_url": video_url, "task_id": task_id}

            elif status == "failed":
                msg = task.get("task_status_msg", "unknown")
                raise RuntimeError(f"Kling task failed: {msg}")

            elif status in ("submitted", "processing"):
                logger.debug("Kling task %s: %s", task_id, status)
                continue

            else:
                raise RuntimeError(f"Kling unknown status: {status}")

        raise RuntimeError(f"Kling task timed out after {poll_timeout}s")
    finally:
        if own_client:
            await client.aclose()
