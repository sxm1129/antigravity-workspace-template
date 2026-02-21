"""Prompt Polish Agent — enhances AI generation prompts for better quality.

Adds cinematic language, character consistency constraints, and style uniformity.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from app.services.agents.agent_framework import Agent, tool, AgentResult

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------

@tool(description="Enhance an image generation prompt with cinematic details (lighting, composition, camera angle, color palette). Return the enhanced prompt string.")
async def enhance_visual_prompt(prompt: str, style: str) -> str:
    """Enhance visual prompt with cinematic details."""
    from app.services.llm_client import llm_call
    result = await llm_call(
        system_prompt=(
            "你是一个专业的AI绘画提示词工程师。增强以下提示词:\n"
            "1. 补充光影描述(lighting)\n"
            "2. 补充构图信息(composition)\n"
            "3. 补充镜头角度(camera angle)\n"
            "4. 补充色彩调性(color palette)\n"
            "5. 确保风格统一\n\n"
            "只返回增强后的英文提示词，不需要其他解释。"
        ),
        user_prompt=f"原始提示词: {prompt}\n目标风格: {style}",
        caller="enhance_visual_prompt",
    )
    return result


@tool(description="Add character consistency constraints to a prompt based on character reference descriptions. Return modified prompt.")
async def add_character_consistency(prompt: str, character_descriptions: str) -> str:
    """Add character consistency to prompt."""
    from app.services.llm_client import llm_call
    result = await llm_call(
        system_prompt=(
            "在图片提示词中嵌入角色一致性约束。\n"
            "确保角色的外貌、服装、发型等与参考描述一致。\n"
            "只返回修改后的英文提示词。"
        ),
        user_prompt=f"提示词: {prompt}\n\n角色描述:\n{character_descriptions}",
        caller="add_character_consistency",
    )
    return result


@tool(description="Translate a Chinese visual description to an optimized English image generation prompt.")
async def translate_to_prompt(chinese_description: str) -> str:
    """Translate Chinese description to English prompt."""
    from app.services.llm_client import llm_call
    result = await llm_call(
        system_prompt=(
            "将中文视觉描述翻译为高质量的英文AI图片生成提示词。\n"
            "注意:\n"
            "1. 使用AI绘画领域的专业术语\n"
            "2. 补充适当的质量标签(masterpiece, best quality等)\n"
            "3. 组织为逻辑清晰的提示词结构\n"
            "只返回英文提示词。"
        ),
        user_prompt=chinese_description,
        caller="translate_to_prompt",
    )
    return result


@tool(description="Generate a motion/camera movement description for video generation from a scene description.")
async def generate_motion_prompt(scene_description: str) -> str:
    """Generate video motion prompt."""
    from app.services.llm_client import llm_call
    result = await llm_call(
        system_prompt=(
            "为以下场景描述生成视频运动提示词。\n"
            "描述镜头运动(推/拉/摇/移/升/降)和画面内的动作。\n"
            "输出简洁的英文运动描述。"
        ),
        user_prompt=scene_description,
        caller="generate_motion_prompt",
    )
    return result


# ---------------------------------------------------------------------------
# Prompt Agent
# ---------------------------------------------------------------------------

PROMPT_SYSTEM_PROMPT = """你是 MotionWeaver 的提示词优化 Agent。

你的任务是增强 AI 图片/视频生成的提示词质量。你有以下工具:

1. **enhance_visual_prompt** — 增强视觉提示词(光影/构图/色彩)
2. **add_character_consistency** — 添加角色一致性约束
3. **translate_to_prompt** — 将中文描述翻译为英文提示词
4. **generate_motion_prompt** — 生成视频运动提示词

## 工作流程:
1. 如果输入是中文，先调用 translate_to_prompt
2. 调用 enhance_visual_prompt 增强视觉细节
3. 如有角色信息，调用 add_character_consistency
4. 如需视频提示词，调用 generate_motion_prompt
5. 返回最终的优化提示词

## 输出:
返回优化后的英文提示词(image_prompt)和运动提示词(motion_prompt, 如适用)。
"""


def create_prompt_agent(*, on_step=None, model: str | None = None) -> Agent:
    """Create a Prompt Polish Agent instance."""
    return Agent(
        name="PromptAgent",
        system_prompt=PROMPT_SYSTEM_PROMPT,
        tools=[
            enhance_visual_prompt,
            add_character_consistency,
            translate_to_prompt,
            generate_motion_prompt,
        ],
        model=model,
        max_iterations=8,
        max_tokens=4096,
        temperature=0.6,
        on_step=on_step,
    )


async def polish_prompt(
    description: str,
    *,
    style: str = "cinematic anime",
    character_descriptions: str | None = None,
    include_motion: bool = False,
    on_step=None,
    model: str | None = None,
) -> AgentResult:
    """Public API: Polish a scene description into optimized generation prompts.

    Args:
        description: Scene description (Chinese or English).
        style: Target visual style.
        character_descriptions: Character appearance descriptions for consistency.
        include_motion: Whether to also generate a motion prompt for video.

    Returns:
        AgentResult with enhanced prompts.
    """
    agent = create_prompt_agent(on_step=on_step, model=model)

    msg = f"优化以下场景描述为高质量的AI生成提示词。风格: {style}\n\n场景描述: {description}"
    if character_descriptions:
        msg += f"\n\n角色描述:\n{character_descriptions}"
    if include_motion:
        msg += "\n\n请同时生成视频运动提示词。"

    return await agent.run(msg)
