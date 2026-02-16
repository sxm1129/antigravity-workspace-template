from __future__ import annotations
"""Styles API — list and preview style presets."""

from fastapi import APIRouter

from app.prompts.manager import PromptManager

router = APIRouter()

STYLE_META = {
    "default": {
        "name": "默认",
        "description": "通用漫剧风格,平衡的画面表现力",
    },
    "manga_jp": {
        "name": "日漫",
        "description": "日本漫画风格,清晰线条,网点纸,夸张表情",
    },
    "manga_cn": {
        "name": "国漫",
        "description": "中国漫画风格,水墨元素,细腻色彩",
    },
    "comic_us": {
        "name": "美漫",
        "description": "美式漫画风格,粗犷线条,强烈阴影,鲜艳色彩",
    },
}


@router.get("/")
async def list_styles():
    """List all available style presets."""
    available = PromptManager.list_styles()
    styles = []
    for style_id in available:
        meta = STYLE_META.get(style_id, {"name": style_id, "description": ""})
        styles.append({
            "id": style_id,
            "name": meta["name"],
            "description": meta["description"],
            "templates": PromptManager.list_templates(style_id),
        })
    return {"styles": styles}


@router.get("/{style_id}")
async def get_style_detail(style_id: str):
    """Get detail for a specific style preset."""
    meta = STYLE_META.get(style_id, {"name": style_id, "description": ""})
    return {
        "id": style_id,
        "name": meta["name"],
        "description": meta["description"],
        "templates": PromptManager.list_templates(style_id),
    }


@router.post("/reload")
async def reload_prompts():
    """Reload prompt template cache (admin use)."""
    PromptManager.reload()
    return {"status": "reloaded"}


@router.get("/{style_id}/prompts/{template_name}")
async def get_prompt_template(style_id: str, template_name: str):
    """Get the raw content of a prompt template for editing.

    Example: GET /api/styles/default/prompts/outline
    """
    content = PromptManager.get_prompt(template_name, style_id)
    if not content:
        from fastapi import HTTPException
        raise HTTPException(
            status_code=404,
            detail=f"Prompt template '{template_name}' not found for style '{style_id}'",
        )
    return {"style": style_id, "template": template_name, "content": content}
