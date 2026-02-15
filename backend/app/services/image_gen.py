from __future__ import annotations
"""Image generation service — uses Gemini 2.5 Flash via OpenRouter.

Gemini 2.5 Flash supports native image generation (multimodal output).
We send a visual prompt and receive a generated image in the response.
Images are saved to local media_volume.
"""

import base64
import logging
import os

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

OPENROUTER_URL = f"{settings.OPENROUTER_BASE_URL}/chat/completions"

IMAGE_SYSTEM_PROMPT = """你是一位专业的漫画/动漫插画师。请根据用户提供的详细画面描述，
生成一张高质量的漫剧风格插画。

要求：
- 画风统一、细腻，适合漫剧作品
- 画面比例为 16:9 (1920x1080)
- 构图、光影、色调要符合描述中的要求
- 人物外貌、表情、服装要精准还原描述"""


async def generate_image(
    prompt_visual: str,
    project_id: str,
    scene_id: str,
    sfx_text: str | None = None,
    identity_refs: list[str] | None = None,
) -> str:
    """Generate an image for a scene and save to media_volume.

    Args:
        prompt_visual: Visual prompt for image generation.
        project_id: Project ID for directory organization.
        scene_id: Scene ID for file naming.
        sfx_text: Text to render on the image (SFX).
        identity_refs: List of local paths to character reference images.

    Returns:
        Relative path to the generated image in media_volume.
    """
    if settings.USE_MOCK_API:
        return _mock_image(project_id, scene_id, prompt_visual)

    # Build the prompt with SFX text if provided
    full_prompt = prompt_visual
    if sfx_text:
        full_prompt += f"\n\n画面上需要渲染的文字效果: {sfx_text}"

    # Build messages for the image gen request
    messages: list[dict] = [
        {"role": "system", "content": IMAGE_SYSTEM_PROMPT},
    ]

    # If identity reference images are provided, include them as context
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

    async with httpx.AsyncClient(timeout=180.0) as client:
        response = await client.post(OPENROUTER_URL, headers=headers, json=body)
        response.raise_for_status()

    data = response.json()

    # Parse response — look for inline image data
    choice = data["choices"][0]["message"]
    image_data = None

    # OpenRouter returns images in a separate "images" array on the message
    images_list = choice.get("images", [])
    if images_list:
        for img_part in images_list:
            if img_part.get("type") == "image_url":
                image_url = img_part.get("image_url", {}).get("url", "")
                if image_url.startswith("data:"):
                    b64_str = image_url.split(",", 1)[1] if "," in image_url else image_url
                    image_data = base64.b64decode(b64_str)
                elif image_url:
                    image_data = await _download_bytes(image_url)
                if image_data:
                    break

    # Fallback: check multimodal content array (standard OpenAI format)
    if not image_data and isinstance(choice.get("content"), list):
        for part in choice["content"]:
            if part.get("type") == "image_url":
                image_url = part["image_url"]["url"]
                if image_url.startswith("data:"):
                    b64_str = image_url.split(",", 1)[1] if "," in image_url else image_url
                    image_data = base64.b64decode(b64_str)
                else:
                    image_data = await _download_bytes(image_url)
                break

    if not image_data:
        logger.warning(
            "Image model returned no image data. content_type=%s, images_count=%d, keys=%s",
            type(choice.get("content")).__name__,
            len(images_list),
            list(data.keys()),
        )
        raise RuntimeError(
            f"Image generation failed: model returned no image data. "
            f"Response keys: {list(data.keys())}"
        )

    # Save to media_volume
    rel_path = _save_image(image_data, project_id, scene_id)
    logger.info("Image saved: %s (%d bytes)", rel_path, len(image_data))
    return rel_path


async def _download_bytes(url: str) -> bytes:
    """Download binary content from URL."""
    async with httpx.AsyncClient(timeout=60.0) as client:
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


async def _download_image(url: str, project_id: str, scene_id: str) -> str:
    """Download image from URL, stream to disk."""
    dir_path = os.path.join(settings.MEDIA_VOLUME, project_id, "images")
    os.makedirs(dir_path, exist_ok=True)

    filename = f"{scene_id}.png"
    filepath = os.path.join(dir_path, filename)

    async with httpx.AsyncClient(timeout=60.0) as client:
        async with client.stream("GET", url) as response:
            response.raise_for_status()
            with open(filepath, "wb") as f:
                async for chunk in response.aiter_bytes(chunk_size=8192):
                    f.write(chunk)

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
