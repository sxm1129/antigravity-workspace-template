from __future__ import annotations
"""Character reference image generation — creates visual identity sheets."""

import logging
from typing import Optional

from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


async def generate_character_reference(
    character_name: str,
    appearance_prompt: str,
    project_id: str,
    character_id: str,
    style: str = "default",
) -> str:
    """Generate a character reference sheet (frontal view, high detail).

    Returns the relative media path of the saved image.
    """
    from app.services.image_gen import generate_image

    style_guides = {
        "default": "manga style illustration",
        "manga_jp": "Japanese manga style, clean line art, screentone",
        "manga_cn": "Chinese manhua style, flowing ink, delicate color",
        "comic_us": "American comic book style, bold outlines, strong shadows",
    }
    style_guide = style_guides.get(style, style_guides["default"])

    design_prompt = (
        f"Character design reference sheet, {style_guide}:\n"
        f"Character: {character_name}\n"
        f"Appearance: {appearance_prompt}\n\n"
        f"Requirements:\n"
        f"- Clean frontal view on plain white background\n"
        f"- Full body visible, showing complete outfit\n"
        f"- Consistent proportions, high detail on face and hair\n"
        f"- Neutral expression suitable as reference\n"
        f"- Single character only, no background scenery"
    )

    ref_path = await generate_image(
        prompt_visual=design_prompt,
        project_id=project_id,
        scene_id=f"char_ref_{character_id}",
        sfx_text=None,
    )
    return ref_path


async def build_character_context(project_id: str) -> tuple[str, list[str]]:
    """Build character appearance context and gather reference image paths.

    Returns:
        (char_prompt_block, list_of_reference_image_paths)
    """
    from sqlalchemy import select
    from app.database import async_session_factory
    from app.models.character import Character

    async with async_session_factory() as session:
        result = await session.execute(
            select(Character).where(Character.project_id == project_id)
        )
        characters = result.scalars().all()

    if not characters:
        return "", []

    prompt_lines = ["[Character Visual Consistency Rules]"]
    ref_paths = []

    for ch in characters:
        if ch.appearance_prompt:
            prompt_lines.append(f"- {ch.name}: {ch.appearance_prompt}")
            if ch.style_tags:
                tags = ch.style_tags if isinstance(ch.style_tags, list) else []
                prompt_lines.append(f"  Tags: {', '.join(tags)}")
        if ch.reference_image_path:
            ref_paths.append(ch.reference_image_path)

    return "\n".join(prompt_lines), ref_paths
