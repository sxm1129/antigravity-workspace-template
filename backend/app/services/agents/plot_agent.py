"""PlotAgent — Step 3: Design story arc and episode structure."""

from __future__ import annotations

import json
from typing import Any

from .base import BaseAgent, IntentResult, WorldResult, PlotResult

_DEFAULT_PROMPT = """\
你是一位资深的漫剧编剧和故事架构师。根据用户提供的故事灵感、创意分析和世界观设定，
设计完整的故事架构和分集大纲。

请严格以 JSON 格式输出以下结构：
{
  "theme_statement": "故事主题陈述（一句话概括故事要传达的核心思想）",
  "core_conflict": "核心冲突描述（50-100字，故事的主要矛盾是什么）",
  "story_arc": {
    "opening": "开端（50-80字，如何引入故事）",
    "development": "发展（50-80字，矛盾如何升级）",
    "climax": "高潮（50-80字，最紧张的时刻）",
    "resolution": "结局（50-80字，如何收束）"
  },
  "episodes": [
    {
      "number": 1,
      "title": "集标题（简洁有力）",
      "synopsis": "本集概要（100-150字，包含主要事件、角色互动和情感变化）"
    }
  ]
}

要求：
- episodes 数量为 3-6 集，视故事复杂度而定
- 每集的 synopsis 必须引用世界观中的角色名和地点名
- 故事弧线要有起承转合的节奏感
- 核心冲突要与故事灵感直接相关
- 如果是轻松题材（如亲子出游），冲突可以是温和的（好奇心驱动、小挫折等），不必强行加入激烈对抗
"""


class PlotAgent(BaseAgent):
    """Designs story arc, conflict, and episode breakdown from prior context."""

    name = "plot"
    label = "剧情架构"

    def build_system_prompt(self, style: str) -> str:
        template = self._get_template("agent_plot", style)
        return template or _DEFAULT_PROMPT

    def build_user_prompt(self, logline: str, **context: Any) -> str:
        intent: IntentResult | None = context.get("intent")
        world: WorldResult | None = context.get("world")
        parts = [f"故事灵感：{logline}"]
        if intent:
            parts.append(f"\n创意分析：\n{json.dumps(intent.model_dump(), ensure_ascii=False, indent=2)}")
        if world:
            parts.append(f"\n世界观设定：\n{json.dumps(world.model_dump(), ensure_ascii=False, indent=2)}")
        return "\n".join(parts)

    def parse_response(self, raw: str) -> PlotResult:
        data = self._extract_json(raw)
        return PlotResult(**data)
