"""Vidu video generation provider.

Ported from DolphinToonFlow Toonflow-app/src/utils/ai/video/owned/vidu.ts.

Supports:
- viduq3-pro, viduq2-pro/-fast/-turbo, viduq1/-classic, vidu2.0
- Text-to-video and image-to-video (single/reference/start-end)
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)

_DEFAULT_T2V_URL = "https://api.vidu.cn/ent/v2/text2video"
_DEFAULT_I2V_URL = "https://api.vidu.cn/ent/v2/img2video"
_DEFAULT_QUERY_URL = "https://api.vidu.cn/ent/v2/tasks"


async def generate_video(
    *,
    prompt: str,
    model: str,
    api_key: str,
    base_url: str | None = None,
    image_base64: list[str] | None = None,
    duration: int = 5,
    resolution: str = "720p",
    aspect_ratio: str = "16:9",
    audio: bool = False,
    has_audio_support: bool = False,
    http_client: httpx.AsyncClient | None = None,
    poll_interval: int = 10,
    poll_timeout: int = 600,
) -> dict[str, Any]:
    """Generate video via Vidu API.

    Returns dict with 'video_url' key on success.
    """
    if not api_key:
        raise ValueError("Vidu API key is required")

    # Parse base_url: "t2v_url|i2v_url|query_url"
    if base_url:
        parts = base_url.split("|")
        t2v_url = parts[0] if len(parts) > 0 else _DEFAULT_T2V_URL
        i2v_url = parts[1] if len(parts) > 1 else _DEFAULT_I2V_URL
        query_url = parts[2] if len(parts) > 2 else _DEFAULT_QUERY_URL
    else:
        t2v_url, i2v_url, query_url = _DEFAULT_T2V_URL, _DEFAULT_I2V_URL, _DEFAULT_QUERY_URL

    authorization = f"Token {api_key}"
    headers = {
        "Content-Type": "application/json",
        "Authorization": authorization,
    }

    has_images = bool(image_base64 and len(image_base64) > 0)

    client = http_client or httpx.AsyncClient(timeout=30.0)
    own_client = http_client is None

    try:
        if not has_images:
            # Text-to-video
            body: dict[str, Any] = {
                "model": model,
                "prompt": prompt,
                "duration": duration,
                "resolution": resolution,
                "aspect_ratio": aspect_ratio,
            }
            if has_audio_support and audio:
                body["audio"] = True
            resp = await client.post(t2v_url, json=body, headers=headers)
        else:
            # Image-to-video
            body = {
                "model": model,
                "images": image_base64,
                "duration": duration,
                "resolution": resolution,
            }
            if prompt:
                body["prompt"] = prompt
            if has_audio_support and audio:
                body["audio"] = True
            resp = await client.post(i2v_url, json=body, headers=headers)

        resp.raise_for_status()
        task_id = resp.json().get("task_id")
        if not task_id:
            raise RuntimeError("Vidu task creation failed: no task_id")

        logger.info("Vidu task created: %s (model=%s)", task_id, model)

        # Poll for completion
        elapsed = 0
        while elapsed < poll_timeout:
            await asyncio.sleep(poll_interval)
            elapsed += poll_interval

            poll_resp = await client.get(
                query_url,
                headers=headers,
                params={"task_ids": task_id},
            )
            poll_resp.raise_for_status()
            tasks = poll_resp.json().get("tasks", [])

            if not tasks:
                logger.warning("Vidu: no tasks returned for id=%s", task_id)
                continue

            task = tasks[0]
            state = task.get("state")

            if state == "success":
                creation = task.get("creations", [{}])[0]
                video_url = creation.get("url")
                if not video_url:
                    raise RuntimeError("Vidu task succeeded but no video URL")
                return {"video_url": video_url, "task_id": task_id}

            elif state == "failed":
                raise RuntimeError("Vidu task failed")

            elif state in ("created", "queueing", "processing"):
                logger.debug("Vidu task %s: %s", task_id, state)
                continue

            else:
                raise RuntimeError(f"Vidu unknown state: {state}")

        raise RuntimeError(f"Vidu task timed out after {poll_timeout}s")
    finally:
        if own_client:
            await client.aclose()
