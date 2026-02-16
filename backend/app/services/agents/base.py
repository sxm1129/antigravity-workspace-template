"""Base agent class and shared data models for the multi-agent pipeline."""

from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from typing import Any

import httpx
from pydantic import BaseModel, Field

from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

OPENROUTER_URL = f"{settings.OPENROUTER_BASE_URL}/chat/completions"

# Shared HTTP client for LLM calls — reuse connections across agents
_http_client: httpx.AsyncClient | None = None


def _get_http_client() -> httpx.AsyncClient:
    """Lazy-init a shared httpx client with long timeout."""
    global _http_client
    if _http_client is None or _http_client.is_closed:
        _http_client = httpx.AsyncClient(timeout=180.0)
    return _http_client


# ---------------------------------------------------------------------------
# Structured data models — JSON contracts between agents
# ---------------------------------------------------------------------------

class IntentResult(BaseModel):
    """Output of IntentAgent: identifies the creative direction."""
    genre: str = Field(description="故事类型，如 亲子/冒险/历史/校园/科幻/都市 等")
    era: str = Field(description="时代背景，如 现代/古代/未来/架空 等")
    tone: str = Field(description="情感基调，如 温馨/热血/悬疑/搞笑 等")
    location_hint: str = Field(description="核心场景提示，如 北京货运火车站/宫廷/太空站")
    target_audience: str = Field(description="目标受众，如 8-12岁儿童/青年/全年龄")
    story_type: str = Field(description="叙事类型，如 成长/冒险/爱情/悬疑推理/家庭温情")
    keywords: list[str] = Field(default_factory=list, description="从 logline 提取的关键词")


class CharacterInfo(BaseModel):
    """A single character in the story."""
    name: str = Field(description="角色姓名")
    identity: str = Field(description="角色身份，如 10岁小男孩/穿越者/太医")
    appearance: str = Field(description="外貌特征描述")
    personality: str = Field(description="性格特点")
    motivation: str = Field(description="角色动机和目标")


class LocationInfo(BaseModel):
    """A notable location in the story world."""
    name: str = Field(description="地点名称")
    description: str = Field(description="地点描述和氛围")


class WorldResult(BaseModel):
    """Output of WorldBuildingAgent: world and characters."""
    setting: str = Field(description="世界观整体描述")
    world_rules: list[str] = Field(default_factory=list, description="世界核心规则")
    characters: list[CharacterInfo] = Field(default_factory=list, description="角色列表")
    locations: list[LocationInfo] = Field(default_factory=list, description="重要地点列表")


class EpisodeInfo(BaseModel):
    """A single episode in the story arc."""
    number: int = Field(description="集数编号")
    title: str = Field(description="集标题")
    synopsis: str = Field(description="本集概要")


class PlotResult(BaseModel):
    """Output of PlotAgent: story structure and episodes."""
    theme_statement: str = Field(description="主题陈述")
    core_conflict: str = Field(description="核心冲突")
    story_arc: dict[str, str] = Field(
        default_factory=dict,
        description="故事弧线: {opening, development, climax, resolution}",
    )
    episodes: list[EpisodeInfo] = Field(default_factory=list, description="分集列表")


# ---------------------------------------------------------------------------
# Pipeline event model — for SSE streaming
# ---------------------------------------------------------------------------

class PipelineEvent(BaseModel):
    """An event emitted during pipeline execution."""
    event_type: str  # step_start, step_complete, pipeline_complete, error
    step: str | None = None  # intent, world, plot, assemble
    label: str | None = None  # 用户可读的步骤名称
    index: int | None = None  # 0-3
    total: int = 4
    result: dict[str, Any] | None = None  # JSON result of a step
    outline: str | None = None  # final markdown (pipeline_complete only)
    error: str | None = None


# ---------------------------------------------------------------------------
# Base agent
# ---------------------------------------------------------------------------

class BaseAgent(ABC):
    """Abstract base for all pipeline agents."""

    name: str = "base"
    label: str = "Base Agent"

    @abstractmethod
    def build_system_prompt(self, style: str) -> str:
        """Build the system prompt, optionally using a style-specific template."""
        ...

    @abstractmethod
    def build_user_prompt(self, logline: str, **context: Any) -> str:
        """Build the user prompt from logline + prior agent results."""
        ...

    @abstractmethod
    def parse_response(self, raw: str) -> BaseModel:
        """Parse the raw LLM response into the structured data model."""
        ...

    async def run(self, logline: str, style: str = "default", **context: Any) -> BaseModel:
        """Execute the agent: build prompts → call LLM → parse response."""
        system_prompt = self.build_system_prompt(style)
        user_prompt = self.build_user_prompt(logline, **context)

        raw = await self._call_llm(system_prompt, user_prompt, json_mode=True)
        return self.parse_response(raw)

    async def _call_llm(
        self,
        system_prompt: str,
        user_prompt: str,
        json_mode: bool = False,
    ) -> str:
        """Call OpenRouter chat completions API."""
        headers = {
            "Authorization": f"Bearer {settings.OPENROUTER_API_KEY}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://motionweaver.app",
            "X-Title": "MotionWeaver",
        }

        body: dict = {
            "model": settings.STORY_MODEL,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.8,
            "max_tokens": 8192,
        }
        if json_mode:
            body["response_format"] = {"type": "json_object"}

        logger.info(
            "[%s] Calling LLM model=%s json_mode=%s",
            self.name, settings.STORY_MODEL, json_mode,
        )

        client = _get_http_client()
        response = await client.post(OPENROUTER_URL, headers=headers, json=body)
        response.raise_for_status()

        data = response.json()
        content = data["choices"][0]["message"]["content"]
        logger.info("[%s] LLM response received, length=%d", self.name, len(content))
        return content

    @staticmethod
    def _extract_json(text: str) -> dict:
        """Extract JSON object from text that may be wrapped in markdown fences."""
        import re
        # Try to find JSON within code fences first
        m = re.search(r'```(?:json)?\s*\n?(.*?)\n?```', text, re.DOTALL)
        if m:
            text = m.group(1).strip()
        try:
            return json.loads(text)
        except json.JSONDecodeError as e:
            logger.error("Failed to parse JSON from LLM response: %s\nRaw text: %.500s", e, text)
            raise ValueError(
                f"LLM 返回的内容无法解析为 JSON，请重试。\n解析错误: {e}"
            ) from e

    @staticmethod
    def _get_template(template_name: str, style: str) -> str | None:
        """Load a prompt template for the given style."""
        from app.prompts.manager import PromptManager
        return PromptManager.get_prompt(template_name, style)
