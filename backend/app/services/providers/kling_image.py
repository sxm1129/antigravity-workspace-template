"""Kling image generation provider.

Supports kling-image-o1 model.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)

_DEFAULT_ENDPOINT = "https://api-beijing.klingai.com/v1/images/generations"


async def generate_image(
    *,
    prompt: str,
    model: str,
    api_key: str,
    base_url: str | None = None,
    image_base64: str | None = None,
    aspect_ratio: str = "16:9",
    http_client: httpx.AsyncClient | None = None,
    poll_interval: int = 5,
    poll_timeout: int = 120,
) -> dict[str, Any]:
    """Generate image via Kling Image API.

    Returns dict with 'image_url' key.
    """
    if not api_key:
        raise ValueError("Kling API key is required")

    endpoint = base_url or _DEFAULT_ENDPOINT
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    body: dict[str, Any] = {
        "model_name": model,
        "prompt": prompt,
        "aspect_ratio": aspect_ratio,
        "n": 1,
    }

    if image_base64:
        import re
        body["image"] = re.sub(r"^data:image/[^;]+;base64,", "", image_base64)

    client = http_client or httpx.AsyncClient(timeout=30.0)
    own_client = http_client is None

    try:
        resp = await client.post(endpoint, json=body, headers=headers)
        resp.raise_for_status()
        result = resp.json()

        if result.get("code") != 0:
            raise RuntimeError(f"Kling image error: {result.get('message')}")

        task_id = result.get("data", {}).get("task_id")
        if not task_id:
            raise RuntimeError("Kling image: no task_id")

        logger.info("Kling image task: %s (model=%s)", task_id, model)

        # Poll
        query_url = f"{endpoint}/{task_id}"
        elapsed = 0
        while elapsed < poll_timeout:
            await asyncio.sleep(poll_interval)
            elapsed += poll_interval

            poll_resp = await client.get(query_url, headers=headers)
            poll_resp.raise_for_status()
            poll_data = poll_resp.json()
            task = poll_data.get("data", {})
            status = task.get("task_status")

            if status == "succeed":
                images = task.get("task_result", {}).get("images", [])
                if images:
                    return {"image_url": images[0].get("url"), "task_id": task_id}
                raise RuntimeError("Kling image: no images in result")
            elif status == "failed":
                raise RuntimeError(f"Kling image failed: {task.get('task_status_msg')}")

        raise RuntimeError(f"Kling image timed out after {poll_timeout}s")
    finally:
        if own_client:
            await client.aclose()
