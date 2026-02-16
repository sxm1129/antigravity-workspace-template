"""IntentAgent — Step 1: Identify creative direction from logline."""

from __future__ import annotations

from typing import Any

from .base import BaseAgent, IntentResult

_DEFAULT_PROMPT = """\
你是一位专业的故事创意分析师。请分析用户提供的一句话灵感（logline），
识别其中的创作意图和方向。

请严格以 JSON 格式输出以下字段：
{
  "genre": "故事类型（如：亲子/冒险/历史/校园/科幻/都市/悬疑/奇幻/职场 等）",
  "era": "时代背景（如：现代/古代/未来/架空 等）",
  "tone": "情感基调（如：温馨/热血/悬疑/搞笑/感人/紧张 等）",
  "location_hint": "核心场景提示（从 logline 中提取的主要场景）",
  "target_audience": "目标受众（如：8-12岁儿童/青少年/成人/全年龄）",
  "story_type": "叙事类型（如：成长/冒险/爱情/悬疑推理/家庭温情/热血战斗）",
  "keywords": ["从 logline 提取的关键词列表"]
}

注意：
- 仔细分析 logline 中隐含的情感、场景和人物关系
- keywords 应提取 logline 中具有叙事价值的核心名词和概念
- 所有字段必须基于 logline 推断，不要编造不存在的内容
"""


class IntentAgent(BaseAgent):
    """Identifies creative direction, genre, tone, and keywords from logline."""

    name = "intent"
    label = "意图识别"

    def build_system_prompt(self, style: str) -> str:
        template = self._get_template("agent_intent", style)
        return template or _DEFAULT_PROMPT

    def build_user_prompt(self, logline: str, **context: Any) -> str:
        return f"故事灵感：{logline}"

    def parse_response(self, raw: str) -> IntentResult:
        data = self._extract_json(raw)
        return IntentResult(**data)
