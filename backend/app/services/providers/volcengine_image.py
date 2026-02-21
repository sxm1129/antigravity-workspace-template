"""Volcengine (Doubao Seedream) image generation provider.

Supports doubao-seedream-4-5 and doubao-seedream-4-0 models.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)

_DEFAULT_ENDPOINT = "https://ark.cn-beijing.volces.com/api/v3"


async def generate_image(
    *,
    prompt: str,
    model: str,
    api_key: str,
    base_url: str | None = None,
    image_base64: str | None = None,
    http_client: httpx.AsyncClient | None = None,
    poll_interval: int = 5,
    poll_timeout: int = 120,
) -> dict[str, Any]:
    """Generate image via Volcengine Seedream API.

    Returns dict with 'image_url' or 'image_data' key.
    """
    if not api_key:
        raise ValueError("Volcengine API key is required")

    endpoint = base_url or _DEFAULT_ENDPOINT
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    body: dict[str, Any] = {
        "model": model,
        "content": [{"type": "text", "text": prompt}],
    }

    if image_base64:
        body["content"].append({
            "type": "image_url",
            "image_url": {"url": image_base64},
        })

    client = http_client or httpx.AsyncClient(timeout=30.0)
    own_client = http_client is None

    try:
        create_url = f"{endpoint}/contents/generations/tasks"
        resp = await client.post(create_url, json=body, headers=headers)
        resp.raise_for_status()
        result = resp.json()

        task_id = result.get("id")
        if not task_id:
            raise RuntimeError(f"Volcengine image task creation failed: {result}")

        logger.info("Volcengine image task: %s (model=%s)", task_id, model)

        elapsed = 0
        while elapsed < poll_timeout:
            await asyncio.sleep(poll_interval)
            elapsed += poll_interval

            poll_resp = await client.get(
                f"{create_url}/{task_id}", headers=headers
            )
            poll_resp.raise_for_status()
            poll_data = poll_resp.json()
            status = poll_data.get("status")

            if status == "succeeded":
                image_url = poll_data.get("content", {}).get("image_url")
                if image_url:
                    return {"image_url": image_url, "task_id": task_id}
                raise RuntimeError("Volcengine image: no URL in response")
            elif status in ("failed", "cancelled"):
                raise RuntimeError(f"Volcengine image task {status}")
            # queued / running — continue

        raise RuntimeError(f"Volcengine image timed out after {poll_timeout}s")
    finally:
        if own_client:
            await client.aclose()
