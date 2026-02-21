"""Vidu image generation provider.

Supports viduq1 (i2i) and viduq2 (ti2i) models.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)

_DEFAULT_ENDPOINT = "https://api.vidu.cn/ent/v2"


async def generate_image(
    *,
    prompt: str,
    model: str,
    api_key: str,
    base_url: str | None = None,
    image_base64: str | None = None,
    resolution: str = "1080p",
    http_client: httpx.AsyncClient | None = None,
    poll_interval: int = 5,
    poll_timeout: int = 120,
) -> dict[str, Any]:
    """Generate image via Vidu API.

    Returns dict with 'image_url' key.
    """
    if not api_key:
        raise ValueError("Vidu API key is required")

    endpoint = base_url or _DEFAULT_ENDPOINT
    headers = {
        "Authorization": f"Token {api_key}",
        "Content-Type": "application/json",
    }

    body: dict[str, Any] = {
        "model": model,
        "prompt": prompt,
        "resolution": resolution,
    }

    if image_base64:
        body["images"] = [image_base64]

    client = http_client or httpx.AsyncClient(timeout=30.0)
    own_client = http_client is None

    try:
        create_url = f"{endpoint}/img2img"
        resp = await client.post(create_url, json=body, headers=headers)
        resp.raise_for_status()
        task_id = resp.json().get("task_id")
        if not task_id:
            raise RuntimeError("Vidu image: no task_id")

        logger.info("Vidu image task: %s (model=%s)", task_id, model)

        query_url = f"{endpoint}/tasks"
        elapsed = 0
        while elapsed < poll_timeout:
            await asyncio.sleep(poll_interval)
            elapsed += poll_interval

            poll_resp = await client.get(
                query_url, headers=headers, params={"task_ids": task_id}
            )
            poll_resp.raise_for_status()
            tasks = poll_resp.json().get("tasks", [])
            if not tasks:
                continue

            task = tasks[0]
            state = task.get("state")

            if state == "success":
                creation = task.get("creations", [{}])[0]
                image_url = creation.get("url")
                if not image_url:
                    raise RuntimeError("Vidu image task succeeded but no URL in response")
                return {"image_url": image_url, "task_id": task_id}
            elif state == "failed":
                raise RuntimeError("Vidu image task failed")

        raise RuntimeError(f"Vidu image timed out after {poll_timeout}s")
    finally:
        if own_client:
            await client.aclose()
