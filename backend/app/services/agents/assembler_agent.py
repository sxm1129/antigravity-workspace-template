"""AssemblerAgent — Step 4: Assemble final Markdown outline from all prior results."""

from __future__ import annotations

import json
from typing import Any

from .base import BaseAgent, IntentResult, WorldResult, PlotResult

_DEFAULT_PROMPT = """\
你是一位专业的漫剧大纲编辑师。根据提供的创意分析、世界观设定和剧情架构，
将所有信息组装成一份完整、格式统一的故事大纲文档。

请用 Markdown 格式输出，结构如下：

# 故事大纲：{故事标题}

## 世界观设定
（融合 setting 和 world_rules，写成流畅的段落）

## 主要角色
### {角色名}
- **身份**：...
- **外貌**：...
- **性格**：...
- **动机**：...
（列出所有角色）

## 主要场景
- **{地点名}**：...
（列出所有地点）

## 故事主线
### 第X集：{标题}
{详细的剧集描述，不少于150字，包含具体场景、角色互动和情感变化}

（列出所有集数）

## 情感基调与风格
（总结整体风格、基调和目标受众）

要求：
- 不要简单罗列 JSON 字段，要用流畅的叙事语言重新组织
- 每集的描述要丰富，包含具体的场景转换和角色对白提示
- 确保所有角色名、地点名与前面的设定一致
- 输出纯 Markdown，不要包含 JSON 或代码块
"""


class AssemblerAgent(BaseAgent):
    """Assembles all structured data into the final Markdown outline."""

    name = "assemble"
    label = "组装大纲"

    def build_system_prompt(self, style: str) -> str:
        template = self._get_template("agent_assembler", style)
        return template or _DEFAULT_PROMPT

    def build_user_prompt(self, logline: str, **context: Any) -> str:
        intent: IntentResult | None = context.get("intent")
        world: WorldResult | None = context.get("world")
        plot: PlotResult | None = context.get("plot")

        parts = [f"故事灵感：{logline}"]
        if intent:
            parts.append(f"\n### 创意分析\n{json.dumps(intent.model_dump(), ensure_ascii=False, indent=2)}")
        if world:
            parts.append(f"\n### 世界观设定\n{json.dumps(world.model_dump(), ensure_ascii=False, indent=2)}")
        if plot:
            parts.append(f"\n### 剧情架构\n{json.dumps(plot.model_dump(), ensure_ascii=False, indent=2)}")
        parts.append("\n请将以上所有内容组装成完整的 Markdown 格式故事大纲。")
        return "\n".join(parts)

    def parse_response(self, raw: str) -> str:
        """AssemblerAgent returns plain Markdown, not JSON."""
        # Strip any stray code fences
        text = raw.strip()
        if text.startswith("```markdown"):
            text = text[len("```markdown"):].strip()
        if text.startswith("```"):
            text = text[3:].strip()
        if text.endswith("```"):
            text = text[:-3].strip()
        return text

    async def run(self, logline: str, style: str = "default", **context: Any) -> str:  # type: ignore[override]
        """Override: AssemblerAgent does NOT use json_mode since it outputs Markdown."""
        system_prompt = self.build_system_prompt(style)
        user_prompt = self.build_user_prompt(logline, **context)
        raw = await self._call_llm(system_prompt, user_prompt, json_mode=False)
        return self.parse_response(raw)
