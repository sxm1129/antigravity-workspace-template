from __future__ import annotations
"""Image generation service — integrates with Nano Banana Pro.

Handles identity-locked image generation with Base64 reference image injection.
All generated images are downloaded and saved to local media_volume.
"""

import base64
import logging
import os

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


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

    # Build payload with Base64 identity references
    payload: dict = {
        "prompt": prompt_visual,
    }

    if sfx_text:
        payload["text_rendering"] = [sfx_text]

    if identity_refs:
        ref_images_b64 = []
        for ref_path in identity_refs:
            full_path = os.path.join(settings.MEDIA_VOLUME, ref_path)
            if os.path.exists(full_path):
                with open(full_path, "rb") as f:
                    img_b64 = base64.b64encode(f.read()).decode("utf-8")
                    ref_images_b64.append(img_b64)
            else:
                logger.warning("Identity ref not found: %s", full_path)

        if ref_images_b64:
            payload["identity_lock"] = {"reference_images": ref_images_b64}

    # Call Nano Banana Pro API
    headers = {
        "Authorization": f"Bearer {settings.NANO_BANANA_API_KEY}",
        "Content-Type": "application/json",
    }

    async with httpx.AsyncClient(timeout=180.0) as client:
        response = await client.post(
            settings.NANO_BANANA_ENDPOINT, headers=headers, json=payload
        )
        response.raise_for_status()

    result = response.json()
    image_url = result.get("image_url") or result.get("url")

    if not image_url:
        raise RuntimeError("Nano Banana API returned no image URL")

    # Download image to local media_volume
    rel_path = await _download_image(image_url, project_id, scene_id)
    logger.info("Image saved: %s", rel_path)
    return rel_path


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
    """Generate a mock placeholder image (solid color JPEG with text).

    Creates a simple colored rectangle as a stand-in for real generation.
    """
    try:
        from PIL import Image, ImageDraw, ImageFont

        img = Image.new("RGB", (1920, 1080), color=(35, 35, 60))
        draw = ImageDraw.Draw(img)

        # Draw prompt text preview
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
        # Fallback: create a minimal 1x1 PNG if PIL not available
        import struct
        dir_path = os.path.join(settings.MEDIA_VOLUME, project_id, "images")
        os.makedirs(dir_path, exist_ok=True)
        filepath = os.path.join(dir_path, f"{scene_id}.png")

        # Minimal valid PNG (1x1 blue pixel)
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
