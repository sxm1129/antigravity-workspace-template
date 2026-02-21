"""Outline Agent — generates structured outlines from loglines or novel chapters.

Inspired by DolphinToonFlow's OutlineScript agent with storyline management.
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

@tool(description="Generate a storyline outline from a logline or chapter summary. Return JSON with title, theme, characters, and episode_outlines.")
async def generate_outline(logline: str, num_episodes: int) -> str:
    """Generate structured outline from a logline."""
    from app.services.llm_client import llm_call
    result = await llm_call(
        system_prompt=(
            "你是一个专业的编剧。根据故事梗概生成结构化大纲。\n"
            "输出JSON格式:\n"
            "{\n"
            '  "title": "作品标题",\n'
            '  "theme": "核心主题",\n'
            '  "characters": [{"name": "角色名", "description": "描述", "traits": ["性格特征"]}],\n'
            '  "episode_outlines": [{"episode": 1, "title": "标题", "summary": "摘要", "key_events": ["事件"]}]\n'
            "}\n只返回JSON。"
        ),
        user_prompt=f"故事梗概: {logline}\n集数: {num_episodes}",
        json_mode=True,
        caller="generate_outline",
    )
    return result


@tool(description="Extract characters from a story outline, including their relationships. Return JSON array.")
async def extract_characters(outline_json: str) -> str:
    """Extract detailed character profiles from outline."""
    from app.services.llm_client import llm_call
    result = await llm_call(
        system_prompt=(
            "从大纲中提取完整的角色档案。\n"
            "输出JSON数组，每个角色:\n"
            "{\n"
            '  "name": "角色名", "english_name": "英文名",\n'
            '  "age": "年龄", "gender": "性别",\n'
            '  "appearance": "外貌描述(用于AI绘画)",\n'
            '  "personality": "性格特征",\n'
            '  "role": "protagonist/antagonist/supporting",\n'
            '  "relationships": [{"character": "对方名", "relation": "关系"}]\n'
            "}\n只返回JSON。"
        ),
        user_prompt=f"大纲:\n{outline_json}",
        json_mode=True,
        caller="extract_characters",
    )
    return result


@tool(description="Expand an episode outline into a full script with dialogue and stage directions.")
async def expand_episode(episode_outline: str, characters_json: str) -> str:
    """Expand episode outline to full script."""
    from app.services.llm_client import llm_call
    result = await llm_call(
        system_prompt=(
            "你是一个专业编剧。将集大纲扩展为完整的短剧剧本。\n"
            "包含: 场景描述、角色对白、动作指令、情绪标注。\n"
            "格式:\n"
            "## 场景 1: [场景名]\n"
            "[场景描述]\n\n"
            "**角色名**: 对白\n"
            "(动作/表情指令)\n\n"
            "输出纯文本剧本。"
        ),
        user_prompt=f"集大纲:\n{episode_outline}\n\n角色档案:\n{characters_json}",
        caller="expand_episode",
    )
    return result


@tool(description="Refine and improve an existing outline based on feedback.")
async def refine_outline(current_outline: str, feedback: str) -> str:
    """Iteratively refine outline."""
    from app.services.llm_client import llm_call
    result = await llm_call(
        system_prompt="你是一个资深编剧。根据反馈优化大纲。保持JSON格式。只返回JSON。",
        user_prompt=f"当前大纲:\n{current_outline}\n\n修改要求:\n{feedback}",
        json_mode=True,
        caller="refine_outline",
    )
    return result


# ---------------------------------------------------------------------------
# Outline Agent
# ---------------------------------------------------------------------------

OUTLINE_SYSTEM_PROMPT = """你是 MotionWeaver 的编剧 Agent。

你的任务是从故事梗概(logline)或小说章节生成结构化的剧本大纲。你有以下工具:

1. **generate_outline** — 从梗概生成大纲(标题/主题/角色/集大纲)
2. **extract_characters** — 从大纲中提取详细角色档案
3. **expand_episode** — 将集大纲扩展为完整剧本
4. **refine_outline** — 根据反馈优化大纲

## 工作流程:
1. 先调用 generate_outline 生成基础大纲
2. 调用 extract_characters 提取角色档案
3. 根据需要调用 expand_episode 扩展剧本
4. 返回完整的大纲和角色数据

## 注意事项:
- 确保角色前后一致
- 每集有明确的冲突和转折
- 对白自然、符合角色性格
"""


def create_outline_agent(*, on_step=None, model: str | None = None) -> Agent:
    """Create an Outline Agent instance."""
    return Agent(
        name="OutlineAgent",
        system_prompt=OUTLINE_SYSTEM_PROMPT,
        tools=[generate_outline, extract_characters, expand_episode, refine_outline],
        model=model,
        max_iterations=10,
        max_tokens=8192,
        temperature=0.8,
        on_step=on_step,
    )


async def generate_full_outline(
    logline: str,
    *,
    num_episodes: int = 5,
    on_step=None,
    model: str | None = None,
) -> AgentResult:
    """Public API: Generate a complete outline with characters and scripts.

    Args:
        logline: Story premise / logline.
        num_episodes: Number of episodes to outline.

    Returns:
        AgentResult with structured outline JSON.
    """
    agent = create_outline_agent(on_step=on_step, model=model)
    return await agent.run(
        f"请为以下故事梗概生成完整的{num_episodes}集短剧大纲，包括角色档案。\n\n故事梗概: {logline}",
    )
