from __future__ import annotations
"""Prompt template manager — loads prompts from files, supports style presets."""

import logging
from pathlib import Path
from typing import ClassVar

logger = logging.getLogger(__name__)

_TEMPLATES_DIR = Path(__file__).parent / "templates"


class PromptManager:
    """Load and cache prompt templates from the filesystem.

    Templates are organized by style:
        prompts/templates/{style}/{template_name}.txt

    Falls back to 'default' style if the requested style doesn't have
    the template.
    """

    _cache: ClassVar[dict[str, str]] = {}

    @classmethod
    def get_prompt(cls, template_name: str, style: str = "default") -> str:
        """Get a prompt template by name and style.

        Falls back to 'default' style if template not found.
        """
        cache_key = f"{style}/{template_name}"
        if cache_key in cls._cache:
            return cls._cache[cache_key]

        # Try requested style first
        path = _TEMPLATES_DIR / style / f"{template_name}.txt"
        if not path.exists() and style != "default":
            path = _TEMPLATES_DIR / "default" / f"{template_name}.txt"

        if not path.exists():
            logger.warning("Prompt template not found: %s/%s.txt", style, template_name)
            return ""

        text = path.read_text(encoding="utf-8").strip()
        cls._cache[cache_key] = text
        return text

    @classmethod
    def reload(cls):
        """Clear cache to force reload on next access."""
        cls._cache.clear()
        logger.info("Prompt template cache cleared.")

    @classmethod
    def list_styles(cls) -> list[str]:
        """List available style presets."""
        if not _TEMPLATES_DIR.exists():
            return ["default"]
        return sorted(d.name for d in _TEMPLATES_DIR.iterdir() if d.is_dir())

    @classmethod
    def list_templates(cls, style: str = "default") -> list[str]:
        """List available templates for a style."""
        style_dir = _TEMPLATES_DIR / style
        if not style_dir.exists():
            return []
        return sorted(f.stem for f in style_dir.glob("*.txt"))
