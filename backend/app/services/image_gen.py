from __future__ import annotations
"""Image generation service — multi-provider (Flux / OpenRouter).

Supports pluggable image generation providers via IMAGE_PROVIDERS config.
Providers are tried in priority order; on failure, the next provider is used.

Refactored to extend BaseGenService for unified retry, fallback, and metrics.
"""

import base64
import logging
import os
import random
from typing import Any

import httpx

from app.config import get_settings
from app.services.base_gen_service import BaseGenService, GenServiceConfig

logger = logging.getLogger(__name__)
settings = get_settings()

OPENROUTER_URL = f"{settings.OPENROUTER_BASE_URL}/chat/completions"

# Module-level httpx client for connection reuse (lazy init)
_http_client: httpx.AsyncClient | None = None


def _get_http_client(timeout: float = 180.0) -> httpx.AsyncClient:
    """Return a module-level httpx.AsyncClient, creating it on first use."""
    global _http_client
    if _http_client is None:
        _http_client = httpx.AsyncClient(timeout=timeout)
    return _http_client

IMAGE_SYSTEM_PROMPT = """你是一位专业的漫画/动漫插画师。请根据用户提供的详细画面描述，
生成一张高质量的漫剧风格插画。

要求：
- 画风统一、细腻，适合漫剧作品
- 画面比例为 16:9 (1920x1080)
- 构图、光影、色调要符合描述中的要求
- 人物外貌、表情、服装要精准还原描述"""


class ImageGenService(BaseGenService[str]):
    """Image generation service wrapping OpenRouter multimodal API.

    Inherits retry, fallback, timeout, and cost tracking from BaseGenService.
    """

    service_name = "image_gen"

    def __init__(self) -> None:
        super().__init__(GenServiceConfig(
            max_retries=2,
            retry_delay=3.0,
            timeout=180.0,
            fallback_enabled=True,
        ))

    async def _generate(self, **kwargs: Any) -> str:
        """Delegate to the core image generation logic."""
        return await _generate_image_core(
            prompt_visual=kwargs["prompt_visual"],
            project_id=kwargs["project_id"],
            scene_id=kwargs["scene_id"],
            sfx_text=kwargs.get("sfx_text"),
            identity_refs=kwargs.get("identity_refs"),
        )

    async def _fallback(self, **kwargs: Any) -> str:
        """Fallback to mock image generation."""
        logger.info("image_gen: using mock fallback for scene=%s", kwargs["scene_id"][:8])
        return _mock_image(kwargs["project_id"], kwargs["scene_id"], kwargs["prompt_visual"])

    def _estimate_cost(self, **kwargs: Any) -> float:
        """Rough cost estimate per image generation call."""
        return 0.02  # ~$0.02 per Gemini image gen call


# Module-level singleton for metrics aggregation
_image_service = ImageGenService()


def get_image_service() -> ImageGenService:
    """Return the singleton ImageGenService for metrics access."""
    return _image_service


async def generate_image(
    prompt_visual: str,
    project_id: str,
    scene_id: str,
    sfx_text: str | None = None,
    identity_refs: list[str] | None = None,
) -> str:
    """Public API — delegates to ImageGenService for retry/fallback/metrics.

    Backward-compatible with existing callers.
    """
    result = await _image_service.execute(
        prompt_visual=prompt_visual,
        project_id=project_id,
        scene_id=scene_id,
        sfx_text=sfx_text,
        identity_refs=identity_refs,
    )
    return result.data


async def _generate_image_core(
    prompt_visual: str,
    project_id: str,
    scene_id: str,
    sfx_text: str | None = None,
    identity_refs: list[str] | None = None,
) -> str:
    """Core image generation logic — called by ImageGenService._generate().

    Routes to the configured provider(s) in IMAGE_PROVIDERS order.
    On failure, falls through to the next provider.
    """
    if settings.USE_MOCK_API:
        return _mock_image(project_id, scene_id, prompt_visual)

    providers = [p.strip() for p in settings.IMAGE_PROVIDERS.split(",") if p.strip()]
    last_error: Exception | None = None

    for provider in providers:
        try:
            if provider == "flux":
                return await _generate_via_flux(
                    prompt_visual, project_id, scene_id,
                )
            elif provider == "openrouter":
                return await _generate_via_openrouter(
                    prompt_visual, project_id, scene_id,
                    sfx_text=sfx_text, identity_refs=identity_refs,
                )
            else:
                logger.warning("Unknown image provider: %s, skipping", provider)
        except Exception as e:
            logger.warning(
                "image_gen provider=%s failed for scene=%s: %s",
                provider, scene_id[:8], e,
            )
            last_error = e
            continue

    raise last_error or RuntimeError("No image providers configured")


# ---------------------------------------------------------------------------
# Provider: Flux (Private Deployment)
# ---------------------------------------------------------------------------

async def _generate_via_flux(
    prompt_visual: str,
    project_id: str,
    scene_id: str,
) -> str:
    """Generate image via Flux private API (OpenAI-compatible images endpoint)."""
    url = f"{settings.FLUX_API_BASE}/images/generations"
    headers = {
        "Authorization": f"Bearer {settings.FLUX_API_KEY}",
        "Content-Type": "application/json",
    }

    seed = random.randint(1, 2**32 - 1)
    payload = {
        "model": settings.FLUX_MODEL,
        "prompt": prompt_visual,
        "n": 1,
        "size": "1920x1080",
        "seed": seed,
    }

    logger.info(
        "Calling Flux image model=%s for scene=%s (seed=%d)",
        settings.FLUX_MODEL, scene_id[:8], seed,
    )

    client = _get_http_client(timeout=float(settings.FLUX_TIMEOUT))
    response = await client.post(url, headers=headers, json=payload)
    response.raise_for_status()

    result = response.json()
    data_list = result.get("data", [])
    if not data_list:
        raise RuntimeError(f"Flux returned empty data. Response keys: {list(result.keys())}")

    item = data_list[0]
    image_data: bytes | None = None

    # Handle b64_json response
    if "b64_json" in item and item["b64_json"]:
        image_data = base64.b64decode(item["b64_json"])

    # Handle URL response
    if not image_data and "url" in item and item["url"]:
        image_data = await _download_bytes(item["url"])

    if not image_data:
        raise RuntimeError("Flux returned no image data (no b64_json or url)")

    rel_path = _save_image(image_data, project_id, scene_id)
    logger.info(
        "Flux image saved: %s (%d bytes, seed=%d)",
        rel_path, len(image_data), seed,
    )
    return rel_path


# ---------------------------------------------------------------------------
# Provider: OpenRouter (Gemini multimodal)
# ---------------------------------------------------------------------------

async def _generate_via_openrouter(
    prompt_visual: str,
    project_id: str,
    scene_id: str,
    sfx_text: str | None = None,
    identity_refs: list[str] | None = None,
) -> str:
    """Generate image via OpenRouter multimodal API (Gemini 2.5 Flash)."""
    full_prompt = prompt_visual
    if sfx_text:
        full_prompt += f"\n\n画面上需要渲染的文字效果: {sfx_text}"

    messages: list[dict] = [
        {"role": "system", "content": IMAGE_SYSTEM_PROMPT},
    ]

    user_content: list[dict] = []
    if identity_refs:
        for ref_path in identity_refs:
            full_path = os.path.join(settings.MEDIA_VOLUME, ref_path)
            if os.path.exists(full_path):
                with open(full_path, "rb") as f:
                    img_b64 = base64.b64encode(f.read()).decode("utf-8")
                user_content.append({
                    "type": "image_url",
                    "image_url": {"url": f"data:image/png;base64,{img_b64}"},
                })
            else:
                logger.warning("Identity ref not found: %s", full_path)

    user_content.append({"type": "text", "text": f"请生成以下画面的插画:\n\n{full_prompt}"})
    messages.append({"role": "user", "content": user_content})

    headers = {
        "Authorization": f"Bearer {settings.OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://motionweaver.app",
        "X-Title": "MotionWeaver",
    }

    body = {
        "model": settings.IMAGE_MODEL,
        "messages": messages,
        "modalities": ["text", "image"],
        "temperature": 0.8,
        "max_tokens": 4096,
    }

    logger.info("Calling OpenRouter image model=%s for scene=%s", settings.IMAGE_MODEL, scene_id[:8])

    client = _get_http_client()
    response = await client.post(OPENROUTER_URL, headers=headers, json=body)
    response.raise_for_status()

    data = response.json()

    if data.get("error"):
        raise RuntimeError(f"Image API error: {data['error']}")

    choices = data.get("choices", [])
    if not choices:
        raise RuntimeError(f"Image generation returned empty choices. Response keys: {list(data.keys())}")

    choice = choices[0]
    finish_reason = choice.get("finish_reason", "")
    if finish_reason in ("content_filter", "safety"):
        raise RuntimeError(
            f"Image blocked by content filter (finish_reason={finish_reason}). "
            "Try rephrasing the visual prompt."
        )

    message = choice.get("message", {})
    image_data = None

    # Strategy 1: OpenRouter "images" array
    images_list = message.get("images", [])
    if images_list:
        for img_part in images_list:
            if img_part.get("type") == "image_url":
                image_url = img_part.get("image_url", {}).get("url", "")
                image_data = await _extract_image_from_url(image_url)
                if image_data:
                    break

    # Strategy 2: Multimodal content array
    if not image_data and isinstance(message.get("content"), list):
        for part in message["content"]:
            if part.get("type") == "image_url":
                url_obj = part.get("image_url", {})
                image_url = url_obj.get("url", "") if isinstance(url_obj, dict) else str(url_obj)
                image_data = await _extract_image_from_url(image_url)
                if image_data:
                    break
            if part.get("type") == "inline_data" or part.get("inline_data"):
                inline = part.get("inline_data", part)
                b64_str = inline.get("data", "")
                if b64_str:
                    image_data = base64.b64decode(b64_str)
                    break

    # Strategy 3: Plain string base64
    if not image_data and isinstance(message.get("content"), str):
        content_str = message["content"].strip()
        if len(content_str) > 1000 and not content_str.startswith("{"):
            try:
                image_data = base64.b64decode(content_str)
                if not (image_data[:4] == b'\x89PNG' or image_data[:2] == b'\xff\xd8'):
                    image_data = None
            except Exception:
                image_data = None

    if not image_data:
        content_preview = str(message.get("content", ""))[:200]
        logger.warning(
            "Image model returned no image data. content_type=%s, images_count=%d, "
            "finish_reason=%s, content_preview=%s",
            type(message.get("content")).__name__,
            len(images_list),
            finish_reason,
            content_preview,
        )
        raise RuntimeError(
            f"Image generation failed: model returned no image data. "
            f"finish_reason={finish_reason}, content_type={type(message.get('content')).__name__}"
        )

    rel_path = _save_image(image_data, project_id, scene_id)
    logger.info("Image saved: %s (%d bytes)", rel_path, len(image_data))
    return rel_path


async def _extract_image_from_url(image_url: str) -> bytes | None:
    """Extract image bytes from a data URI or HTTP URL."""
    if not image_url:
        return None
    try:
        if image_url.startswith("data:"):
            b64_str = image_url.split(",", 1)[1] if "," in image_url else image_url
            return base64.b64decode(b64_str)
        elif image_url.startswith("http"):
            return await _download_bytes(image_url)
    except Exception as e:
        logger.warning("Failed to extract image from URL: %s", e)
    return None


async def _download_bytes(url: str) -> bytes:
    """Download binary content from URL."""
    client = _get_http_client(timeout=60.0)
    response = await client.get(url)
    response.raise_for_status()
    return response.content


def _save_image(image_data: bytes, project_id: str, scene_id: str) -> str:
    """Save image bytes to media_volume directory."""
    dir_path = os.path.join(settings.MEDIA_VOLUME, project_id, "images")
    os.makedirs(dir_path, exist_ok=True)

    filename = f"{scene_id}.png"
    filepath = os.path.join(dir_path, filename)

    with open(filepath, "wb") as f:
        f.write(image_data)

    return f"{project_id}/images/{filename}"






def _mock_image(project_id: str, scene_id: str, prompt: str) -> str:
    """Generate a mock placeholder image (solid color JPEG with text)."""
    try:
        from PIL import Image, ImageDraw, ImageFont

        img = Image.new("RGB", (1920, 1080), color=(35, 35, 60))
        draw = ImageDraw.Draw(img)

        try:
            font = ImageFont.truetype("/System/Library/Fonts/PingFang.ttc", 28)
        except (OSError, IOError):
            font = ImageFont.load_default()

        draw.text((50, 50), f"Scene: {scene_id[:8]}...", fill=(255, 255, 255), font=font)
        wrapped = prompt[:100] + "..." if len(prompt) > 100 else prompt
        draw.text((50, 100), wrapped, fill=(180, 180, 220), font=font)
        draw.text(
            (50, 1000), "[MOCK IMAGE — MotionWeaver]",
            fill=(100, 100, 140), font=font,
        )

        dir_path = os.path.join(settings.MEDIA_VOLUME, project_id, "images")
        os.makedirs(dir_path, exist_ok=True)
        filepath = os.path.join(dir_path, f"{scene_id}.png")
        img.save(filepath, "PNG")

    except ImportError:
        import struct
        dir_path = os.path.join(settings.MEDIA_VOLUME, project_id, "images")
        os.makedirs(dir_path, exist_ok=True)
        filepath = os.path.join(dir_path, f"{scene_id}.png")

        png_data = (
            b'\x89PNG\r\n\x1a\n'
            b'\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02'
            b'\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx'
            b'\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05\x18\xd8N'
            b'\x00\x00\x00\x00IEND\xaeB`\x82'
        )
        with open(filepath, "wb") as f:
            f.write(png_data)

    return f"{project_id}/images/{scene_id}.png"
