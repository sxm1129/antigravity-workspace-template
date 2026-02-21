"""Extended Wan/DashScope video generation provider.

Extends MotionWeaver's existing DashScope integration with the full range
of wan2.x models from DolphinToonFlow.

Supports:
- wan2.6/2.5/2.2 text-to-video (t2v)
- wan2.6/2.5/2.2 image-to-video (i2v)
- wan2.2/wanx2.1 key-frame-to-video (kf2v)
"""

from __future__ import annotations

import asyncio
import base64
import logging
from pathlib import Path
from typing import Any

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

_DASHSCOPE_ENDPOINT = "https://dashscope.aliyuncs.com/api/v1"


async def generate_video(
    *,
    prompt: str,
    model: str,
    api_key: str | None = None,
    base_url: str | None = None,
    image_base64: list[str] | None = None,
    local_image_path: str | None = None,
    duration: int = 5,
    resolution: str = "720p",
    aspect_ratio: str = "16:9",
    audio: bool = False,
    has_audio_support: bool = False,
    http_client: httpx.AsyncClient | None = None,
    poll_interval: int = 10,
    poll_timeout: int = 600,
) -> dict[str, Any]:
    """Generate video via DashScope/Wan API.

    Returns dict with 'video_url' key on success.
    """
    resolved_key = api_key or settings.DASHSCOPE_API_KEY
    if not resolved_key:
        raise ValueError("DashScope API key is required")

    endpoint = base_url or settings.DASHSCOPE_ENDPOINT or _DASHSCOPE_ENDPOINT

    headers = {
        "Authorization": f"Bearer {resolved_key}",
        "Content-Type": "application/json",
        "X-DashScope-Async": "enable",
    }

    has_images = bool(
        (image_base64 and len(image_base64) > 0) or local_image_path
    )

    # Determine API path based on model type
    is_kf2v = "kf2v" in model
    is_t2v = "t2v" in model or not has_images
    is_i2v = "i2v" in model or (has_images and not is_kf2v)

    if is_kf2v:
        api_path = "/services/aigc/video-generation/generation"
    elif is_t2v and not has_images:
        api_path = "/services/aigc/video-generation/generation"
    else:
        api_path = "/services/aigc/image2video/video-synthesis"

    # Build request body
    input_data: dict[str, Any] = {
        "prompt": prompt,
    }

    # Add image if available
    if has_images:
        if local_image_path:
            img_bytes = Path(local_image_path).read_bytes()
            img_b64 = base64.b64encode(img_bytes).decode()
            input_data["img_url"] = f"data:image/png;base64,{img_b64}"
        elif image_base64:
            input_data["img_url"] = image_base64[0]
            if is_kf2v and len(image_base64) > 1:
                input_data["last_img_url"] = image_base64[1]

    parameters: dict[str, Any] = {}
    if resolution:
        parameters["resolution"] = resolution
    if duration:
        parameters["duration"] = duration

    body: dict[str, Any] = {
        "model": model,
        "input": input_data,
    }
    if parameters:
        body["parameters"] = parameters

    client = http_client or httpx.AsyncClient(timeout=30.0)
    own_client = http_client is None

    try:
        # Create task
        create_url = f"{endpoint}{api_path}"
        resp = await client.post(create_url, json=body, headers=headers)
        resp.raise_for_status()
        result = resp.json()

        task_id = result.get("output", {}).get("task_id")
        if not task_id:
            raise RuntimeError(f"DashScope/Wan task creation failed: {result}")

        logger.info("DashScope/Wan task created: %s (model=%s)", task_id, model)

        # Poll for completion
        poll_url = f"{endpoint}/tasks/{task_id}"
        poll_headers = {"Authorization": f"Bearer {resolved_key}"}
        elapsed = 0

        while elapsed < poll_timeout:
            await asyncio.sleep(poll_interval)
            elapsed += poll_interval

            poll_resp = await client.get(poll_url, headers=poll_headers)
            poll_resp.raise_for_status()
            poll_data = poll_resp.json()

            status = poll_data.get("output", {}).get("task_status")

            if status == "SUCCEEDED":
                results = poll_data.get("output", {}).get("results", [])
                if results:
                    video_url = results[0].get("url")
                    if video_url:
                        return {"video_url": video_url, "task_id": task_id}
                # Fallback for older API format
                video_url = poll_data.get("output", {}).get("video_url")
                if video_url:
                    return {"video_url": video_url, "task_id": task_id}
                raise RuntimeError("DashScope task succeeded but no video URL")

            elif status == "FAILED":
                msg = poll_data.get("output", {}).get("message", "unknown")
                raise RuntimeError(f"DashScope task failed: {msg}")

            elif status in ("PENDING", "RUNNING"):
                logger.debug("DashScope task %s: %s", task_id, status)
                continue

            else:
                logger.warning("DashScope unknown status: %s", status)

        raise RuntimeError(f"DashScope task timed out after {poll_timeout}s")
    finally:
        if own_client:
            await client.aclose()
