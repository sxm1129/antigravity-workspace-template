"""Gemini Veo video generation provider.

Supports Veo 3.1, 3.0, 2.0 models via Google AI API.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)

_DEFAULT_ENDPOINT = "https://generativelanguage.googleapis.com/v1beta"


async def generate_video(
    *,
    prompt: str,
    model: str,
    api_key: str,
    base_url: str | None = None,
    image_base64: list[str] | None = None,
    duration: int = 8,
    resolution: str = "720p",
    aspect_ratio: str = "16:9",
    audio: bool = True,
    http_client: httpx.AsyncClient | None = None,
    poll_interval: int = 15,
    poll_timeout: int = 600,
) -> dict[str, Any]:
    """Generate video via Google Gemini Veo API.

    Returns dict with 'video_url' or 'video_data' key on success.
    """
    if not api_key:
        raise ValueError("Gemini API key is required")

    endpoint = base_url or _DEFAULT_ENDPOINT

    # Build generate request
    contents: list[dict[str, Any]] = []
    parts: list[dict[str, Any]] = [{"text": prompt}]

    # Add images if provided
    if image_base64:
        for img in image_base64:
            # Strip data URL prefix if present
            if img.startswith("data:"):
                mime_type = img.split(";")[0].split(":")[1]
                b64_data = img.split(",", 1)[1]
            else:
                mime_type = "image/png"
                b64_data = img
            parts.append({
                "inline_data": {
                    "mime_type": mime_type,
                    "data": b64_data,
                }
            })

    contents.append({"role": "user", "parts": parts})

    # Generation config
    generation_config: dict[str, Any] = {
        "response_modalities": ["video"],
        "video_config": {
            "aspect_ratio": aspect_ratio,
            "duration_seconds": duration,
            "resolution": resolution,
        },
    }

    if audio:
        generation_config["video_config"]["include_audio"] = True

    body = {
        "contents": contents,
        "generationConfig": generation_config,
    }

    # Veo uses generateContent with long-running operation pattern
    generate_url = (
        f"{endpoint}/models/{model}:generateContent"
        f"?key={api_key}"
    )

    client = http_client or httpx.AsyncClient(timeout=60.0)
    own_client = http_client is None

    try:
        resp = await client.post(generate_url, json=body)
        resp.raise_for_status()
        result = resp.json()

        # Check if it's a long-running operation
        operation_name = result.get("name")
        if operation_name:
            # Poll the operation
            poll_url = f"{endpoint}/{operation_name}?key={api_key}"
            elapsed = 0
            while elapsed < poll_timeout:
                await asyncio.sleep(poll_interval)
                elapsed += poll_interval

                poll_resp = await client.get(poll_url)
                poll_resp.raise_for_status()
                poll_data = poll_resp.json()

                if poll_data.get("done"):
                    return _extract_video_from_response(poll_data.get("response", {}))

                if poll_data.get("error"):
                    raise RuntimeError(
                        f"Gemini Veo failed: {poll_data['error'].get('message', 'unknown')}"
                    )

                logger.debug("Gemini Veo operation %s: polling...", operation_name)

            raise RuntimeError(f"Gemini Veo timed out after {poll_timeout}s")
        else:
            # Synchronous response
            return _extract_video_from_response(result)
    finally:
        if own_client:
            await client.aclose()


def _extract_video_from_response(response: dict) -> dict[str, Any]:
    """Extract video data from Gemini API response."""
    candidates = response.get("candidates", [])
    if not candidates:
        raise RuntimeError("Gemini Veo: no candidates in response")

    content = candidates[0].get("content", {})
    parts = content.get("parts", [])

    for part in parts:
        if "inline_data" in part:
            inline = part["inline_data"]
            if inline.get("mime_type", "").startswith("video/"):
                return {
                    "video_data": inline.get("data"),
                    "mime_type": inline.get("mime_type"),
                }
        if "file_data" in part:
            file_data = part["file_data"]
            return {
                "video_url": file_data.get("file_uri"),
                "mime_type": file_data.get("mime_type"),
            }

    raise RuntimeError("Gemini Veo: no video in response")
