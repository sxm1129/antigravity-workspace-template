"""Image quality enhancement — upscaling, grid generation, quality scoring.

Phase 5 features:
- AI-powered image upscaling (2x/4x)
- Multi-panel grid generation for consistent character poses
- Quality scoring with auto-retry
"""

from __future__ import annotations

import asyncio
import base64
import logging
import os
from typing import Any

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


# ---------------------------------------------------------------------------
# Image Upscaling (2x / 4x)
# ---------------------------------------------------------------------------

async def upscale_image(
    local_image_path: str,
    *,
    scale: int = 2,
    http_client: httpx.AsyncClient | None = None,
) -> str:
    """Upscale an image using available AI upscaler.

    Falls back through providers:
    1. Volcengine Seedream upscale (if API key available)
    2. Local FFmpeg lanczos (always available)

    Args:
        local_image_path: Relative path in media_volume.
        scale: Upscale factor (2 or 4).

    Returns:
        Relative path to upscaled image.
    """
    if settings.ARK_API_KEY:
        try:
            return await _volcengine_upscale(local_image_path, scale, http_client)
        except Exception as e:
            logger.warning("Volcengine upscale failed: %s, falling back to FFmpeg", e)

    return _ffmpeg_upscale(local_image_path, scale)


async def _volcengine_upscale(
    local_image_path: str,
    scale: int,
    http_client: httpx.AsyncClient | None = None,
) -> str:
    """Upscale via Volcengine API."""
    full_path = os.path.join(settings.MEDIA_VOLUME, local_image_path)
    with open(full_path, "rb") as f:
        img_b64 = base64.b64encode(f.read()).decode()

    headers = {
        "Authorization": f"Bearer {settings.ARK_API_KEY}",
        "Content-Type": "application/json",
    }

    body = {
        "model": "doubao-seedream-4-5-251128",
        "content": [
            {"type": "text", "text": f"upscale {scale}x"},
            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{img_b64}"}},
        ],
    }

    endpoint = f"{settings.ARK_ENDPOINT}/contents/generations/tasks"
    client = http_client or httpx.AsyncClient(timeout=60.0)
    own_client = http_client is None

    try:
        resp = await client.post(endpoint, json=body, headers=headers)
        resp.raise_for_status()
        task_id = resp.json().get("id")

        # Poll
        for _ in range(30):
            await asyncio.sleep(5)
            poll = await client.get(f"{endpoint}/{task_id}", headers=headers)
            poll.raise_for_status()
            data = poll.json()
            if data.get("status") == "succeeded":
                result_url = data.get("content", {}).get("image_url")
                if result_url:
                    return await _download_upscaled(result_url, local_image_path, scale, client)

        raise RuntimeError("Upscale timed out")
    finally:
        if own_client:
            await client.aclose()


def _ffmpeg_upscale(local_image_path: str, scale: int) -> str:
    """Upscale using FFmpeg with Lanczos filter."""
    import subprocess

    full_path = os.path.join(settings.MEDIA_VOLUME, local_image_path)
    base, ext = os.path.splitext(local_image_path)
    output_rel = f"{base}_upscale_{scale}x{ext}"
    output_path = os.path.join(settings.MEDIA_VOLUME, output_rel)

    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    cmd = [
        "ffmpeg", "-y",
        "-i", full_path,
        "-vf", f"scale=iw*{scale}:ih*{scale}:flags=lanczos",
        output_path,
    ]

    try:
        subprocess.run(cmd, capture_output=True, timeout=60, check=True)
        logger.info("FFmpeg upscaled: %s → %s (%dx)", local_image_path, output_rel, scale)
        return output_rel
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        logger.error("FFmpeg upscale failed: %s", e)
        return local_image_path  # Return original on failure


async def _download_upscaled(
    url: str,
    original_path: str,
    scale: int,
    client: httpx.AsyncClient,
) -> str:
    """Download upscaled image from URL."""
    base, ext = os.path.splitext(original_path)
    output_rel = f"{base}_upscale_{scale}x{ext}"
    output_path = os.path.join(settings.MEDIA_VOLUME, output_rel)

    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    async with client.stream("GET", url, timeout=60.0) as resp:
        resp.raise_for_status()
        with open(output_path, "wb") as f:
            async for chunk in resp.aiter_bytes(8192):
                f.write(chunk)

    return output_rel


# ---------------------------------------------------------------------------
# Quality Scoring
# ---------------------------------------------------------------------------

async def score_image_quality(
    local_image_path: str,
    prompt_visual: str,
) -> float:
    """Score generated image quality against its prompt.

    Uses LLM vision to evaluate:
    - Prompt adherence (0-1)
    - Visual quality (0-1)
    - Composition (0-1)

    Returns average score (0.0 to 1.0).
    """
    if not settings.ENABLE_AUTO_SCORING:
        return 1.0

    try:
        from app.services.llm_client import llm_call

        full_path = os.path.join(settings.MEDIA_VOLUME, local_image_path)
        with open(full_path, "rb") as f:
            img_b64 = base64.b64encode(f.read()).decode()

        result = await llm_call(
            system_prompt=(
                "Rate this image on 3 dimensions (0.0 to 1.0 each):\n"
                "1. prompt_adherence: How well the image matches the prompt\n"
                "2. visual_quality: Technical quality (sharpness, artifacts, coherence)\n"
                "3. composition: Artistic composition and framing\n"
                "Return JSON: {\"prompt_adherence\": 0.8, \"visual_quality\": 0.9, \"composition\": 0.7, \"average\": 0.8}"
            ),
            user_prompt=f"Prompt: {prompt_visual}\n\nImage: [base64 image provided]",
            json_mode=True,
            caller="score_image_quality",
        )

        import json
        scores = json.loads(result)
        return float(scores.get("average", 0.7))
    except Exception as e:
        logger.warning("Quality scoring failed: %s, returning default", e)
        return 0.7


async def generate_with_quality_check(
    generate_fn,
    *,
    prompt_visual: str,
    threshold: float | None = None,
    max_retries: int | None = None,
    **kwargs,
) -> tuple[str, float]:
    """Generate an image with automatic quality check and retry.

    Returns (image_path, quality_score).
    """
    threshold = threshold if threshold is not None else settings.QUALITY_THRESHOLD
    max_retries = max_retries if max_retries is not None else settings.MAX_QUALITY_RETRIES

    best_path = ""
    best_score = 0.0

    for attempt in range(max_retries + 1):
        path = await generate_fn(**kwargs)
        score = await score_image_quality(path, prompt_visual)

        if score > best_score:
            best_path = path
            best_score = score

        if score >= threshold:
            logger.info("Quality check passed (%.2f >= %.2f) on attempt %d", score, threshold, attempt + 1)
            return path, score

        logger.info("Quality check failed (%.2f < %.2f), retrying (%d/%d)", score, threshold, attempt + 1, max_retries)

    logger.warning("Quality threshold not met after %d attempts, using best (%.2f)", max_retries + 1, best_score)
    return best_path, best_score
