"""Storyboard Agent — multi-level agent for scene-to-storyboard generation.

Inspired by DolphinToonFlow's Storyboard agent with segmentAgent/shotAgent/director.

Pipeline:
  Script → SegmentAgent (split into segments) → ShotAgent (generate shots per segment)
  → DirectorAgent (optimize) → Image prompts
"""

from __future__ import annotations

import json
import logging
from typing import Any

from app.services.agents.agent_framework import Agent, tool, invoke_sub_agent, AgentResult

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Tools for the Storyboard Agent
# ---------------------------------------------------------------------------

@tool(description="Split a script into logical segments (beat groups). Return JSON array of segments with index, description, and key_actions.")
async def split_into_segments(script: str) -> str:
    """Use LLM to decompose script into segments."""
    from app.services.llm_client import llm_call
    prompt = (
        "将以下剧本拆分为逻辑片段(segments)。每个片段包含一组连续的动作/情节。\n"
        "返回 JSON 数组，每个元素: {\"index\": 1, \"description\": \"...\", \"key_actions\": [\"...\"]}\n\n"
        f"剧本:\n{script}"
    )
    result = await llm_call(
        system_prompt="你是一个专业的分镜编剧。将剧本拆分为视觉片段。只返回JSON。",
        user_prompt=prompt,
        json_mode=True,
        caller="split_into_segments",
    )
    return result


@tool(description="Generate shot descriptions for a segment. Return JSON array of shots with shot_number, shot_type, description, camera_movement, and dialogue.")
async def generate_shots(segment_description: str, segment_index: int) -> str:
    """Generate individual shots for a segment."""
    from app.services.llm_client import llm_call
    prompt = (
        f"为以下片段生成分镜画面(shots)。\n"
        f"片段 {segment_index}: {segment_description}\n\n"
        "为每个画面生成:\n"
        "- shot_number: 画面编号\n"
        "- shot_type: 景别(特写/中景/远景/全景)\n"
        "- description: 画面描述\n"
        "- camera_movement: 镜头运动(推/拉/摇/移/固定)\n"
        "- dialogue: 对白(如有)\n\n"
        "返回 JSON 数组。"
    )
    result = await llm_call(
        system_prompt="你是一个专业的分镜导演。为每个情节片段设计具体的镜头画面。只返回JSON。",
        user_prompt=prompt,
        json_mode=True,
        caller="generate_shots",
    )
    return result


@tool(description="Generate detailed image prompts for each shot. Return JSON array with shot_number and image_prompt fields.")
async def generate_image_prompts(shots_json: str, style: str) -> str:
    """Generate AI image generation prompts from shot descriptions."""
    from app.services.llm_client import llm_call
    prompt = (
        f"基于以下分镜数据，为每个画面生成高质量的AI图片生成提示词。\n"
        f"风格要求: {style}\n\n"
        f"分镜数据:\n{shots_json}\n\n"
        "为每个画面生成:\n"
        "- shot_number: 画面编号\n"
        "- image_prompt: 详细的英文图片提示词(包含画面内容、光影、构图、风格)\n"
        "- negative_prompt: 负面提示词\n\n"
        "返回 JSON 数组。"
    )
    result = await llm_call(
        system_prompt="你是一个专业的AI绘画提示词工程师。生成高质量、详细的图片提示词。只返回JSON。",
        user_prompt=prompt,
        json_mode=True,
        caller="generate_image_prompts",
    )
    return result


@tool(description="Review and optimize the storyboard for visual coherence, pacing, and storytelling quality. Return improved version.")
async def review_storyboard(storyboard_json: str) -> str:
    """Director agent reviews and optimizes the overall storyboard."""
    from app.services.llm_client import llm_call
    prompt = (
        "作为导演，审阅以下分镜，优化:\n"
        "1. 视觉连续性(前后画面衔接)\n"
        "2. 节奏感(紧张/舒缓交替)\n"
        "3. 叙事完整性\n"
        "4. 镜头语言多样性\n\n"
        f"当前分镜:\n{storyboard_json}\n\n"
        "返回优化后的完整分镜 JSON。如无需修改，返回原始数据。"
    )
    result = await llm_call(
        system_prompt="你是一个资深影视导演。审阅分镜并提出优化建议。只返回JSON。",
        user_prompt=prompt,
        json_mode=True,
        caller="review_storyboard",
    )
    return result


# ---------------------------------------------------------------------------
# Storyboard Agent
# ---------------------------------------------------------------------------

STORYBOARD_SYSTEM_PROMPT = """你是 MotionWeaver 的分镜导演 Agent。

你的任务是将剧本转化为详细的分镜头脚本。你有以下工具可用:

1. **split_into_segments** — 将剧本拆分为逻辑片段
2. **generate_shots** — 为每个片段生成分镜画面
3. **generate_image_prompts** — 为画面生成AI图片提示词
4. **review_storyboard** — 审阅并优化整体分镜

## 工作流程:
1. 先调用 split_into_segments 拆分剧本
2. 对每个片段调用 generate_shots 生成画面
3. 调用 generate_image_prompts 生成图片提示词
4. 调用 review_storyboard 优化整体分镜
5. 返回最终的分镜结果

## 输出格式:
返回完整的分镜 JSON，包含所有画面的描述和提示词。
"""


def create_storyboard_agent(
    *,
    on_step=None,
    model: str | None = None,
) -> Agent:
    """Create a Storyboard Agent instance."""
    return Agent(
        name="StoryboardAgent",
        system_prompt=STORYBOARD_SYSTEM_PROMPT,
        tools=[
            split_into_segments,
            generate_shots,
            generate_image_prompts,
            review_storyboard,
        ],
        model=model,
        max_iterations=15,
        max_tokens=8192,
        temperature=0.7,
        on_step=on_step,
    )


async def generate_storyboard(
    script: str,
    *,
    style: str = "cinematic anime",
    on_step=None,
    model: str | None = None,
) -> AgentResult:
    """Public API: Generate a complete storyboard from a script.

    Args:
        script: The full episode/scene script.
        style: Visual style for image prompts.
        on_step: Callback for streaming progress updates.
        model: Override LLM model.

    Returns:
        AgentResult with the complete storyboard as JSON content.
    """
    agent = create_storyboard_agent(on_step=on_step, model=model)
    return await agent.run(
        f"请为以下剧本生成完整的分镜头脚本。视觉风格: {style}\n\n剧本:\n{script}",
        context={"style": style},
    )
