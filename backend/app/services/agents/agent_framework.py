"""AI Agent framework with LLM function/tool-calling support.

Built on top of MotionWeaver's llm_client.py for multi-key rotation.
Inspired by DolphinToonFlow's Vercel AI SDK agent pattern.

Usage:
    from app.services.agents.agent_framework import Agent, tool

    @tool(description="Search the database for characters")
    async def search_characters(query: str) -> str:
        ...

    agent = Agent(
        name="StoryboardAgent",
        system_prompt="You are a storyboard director...",
        tools=[search_characters],
    )
    result = await agent.run("Create a storyboard for scene 1")
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Awaitable
import inspect

import httpx

from app.config import get_settings
from app.services.llm_client import (
    _get_client,
    _next_key,
    _mask_key,
    _key_failures,
    OPENROUTER_URL,
    LLMError,
)

logger = logging.getLogger(__name__)
settings = get_settings()


# ---------------------------------------------------------------------------
# Tool definition
# ---------------------------------------------------------------------------

@dataclass
class ToolDefinition:
    """A tool that an Agent can invoke."""
    name: str
    description: str
    parameters: dict[str, Any]  # JSON Schema for parameters
    handler: Callable[..., Awaitable[str]]

    def to_openai_schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


def tool(
    *,
    description: str = "",
    parameters: dict[str, Any] | None = None,
) -> Callable:
    """Decorator to register a function as an Agent tool."""
    def decorator(fn: Callable[..., Awaitable[str]]) -> ToolDefinition:
        params = parameters
        if params is None:
            sig = inspect.signature(fn)
            properties = {}
            required = []
            for pname, param in sig.parameters.items():
                if pname in ("self", "cls"):
                    continue
                ptype = "string"
                annotation = param.annotation
                if annotation == int:
                    ptype = "integer"
                elif annotation == float:
                    ptype = "number"
                elif annotation == bool:
                    ptype = "boolean"
                elif annotation == list:
                    ptype = "array"
                properties[pname] = {"type": ptype}
                if param.default is inspect.Parameter.empty:
                    required.append(pname)
            params = {"type": "object", "properties": properties, "required": required}

        return ToolDefinition(
            name=fn.__name__,
            description=description or fn.__doc__ or "",
            parameters=params,
            handler=fn,
        )
    return decorator


# ---------------------------------------------------------------------------
# Agent execution result
# ---------------------------------------------------------------------------

@dataclass
class AgentStep:
    """A single step in an agent's execution."""
    step_type: str  # "tool_call", "tool_result", "response"
    content: str = ""
    tool_name: str = ""
    tool_args: dict[str, Any] = field(default_factory=dict)
    tool_result: str = ""


@dataclass
class AgentResult:
    """Final result from an agent's execution."""
    content: str
    steps: list[AgentStep] = field(default_factory=list)
    total_tokens: int = 0
    model: str = ""


# ---------------------------------------------------------------------------
# Agent class
# ---------------------------------------------------------------------------

class Agent:
    """AI Agent with tool-calling loop (think -> act -> observe)."""

    def __init__(
        self,
        *,
        name: str,
        system_prompt: str,
        tools: list[ToolDefinition] | None = None,
        model: str | None = None,
        max_iterations: int = 10,
        max_tokens: int = 8192,
        temperature: float = 0.7,
        on_step: Callable[[AgentStep], Any] | None = None,
    ):
        self.name = name
        self.system_prompt = system_prompt
        self.tools = tools or []
        self.model = model or settings.STORY_MODEL
        self.max_iterations = max_iterations
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.on_step = on_step
        self._tool_map = {t.name: t for t in self.tools}

    async def run(
        self, user_message: str, *, context: dict[str, Any] | None = None,
    ) -> AgentResult:
        """Execute the agent loop."""
        steps: list[AgentStep] = []
        sys_prompt = self.system_prompt
        if context:
            ctx_str = "\n".join(f"- {k}: {v}" for k, v in context.items())
            sys_prompt += f"\n\n## Current Context\n{ctx_str}"

        messages: list[dict[str, Any]] = [
            {"role": "system", "content": sys_prompt},
            {"role": "user", "content": user_message},
        ]
        tools_schema = [t.to_openai_schema() for t in self.tools] if self.tools else None
        total_tokens = 0

        for iteration in range(self.max_iterations):
            logger.info("[%s] iteration %d/%d", self.name, iteration + 1, self.max_iterations)
            response_data = await self._llm_call(messages, tools_schema)
            total_tokens += response_data.get("usage", {}).get("total_tokens", 0)

            choice = response_data.get("choices", [{}])[0]
            message = choice.get("message", {})
            tool_calls = message.get("tool_calls")

            if tool_calls:
                messages.append(message)
                for tc in tool_calls:
                    fn = tc.get("function", {})
                    tool_name = fn.get("name", "")
                    try:
                        tool_args = json.loads(fn.get("arguments", "{}"))
                    except json.JSONDecodeError:
                        tool_args = {}

                    step = AgentStep(step_type="tool_call", tool_name=tool_name, tool_args=tool_args)
                    steps.append(step)
                    if self.on_step:
                        await _maybe_await(self.on_step, step)

                    result_str = await self._execute_tool(tool_name, tool_args)
                    r_step = AgentStep(step_type="tool_result", tool_name=tool_name, tool_result=result_str)
                    steps.append(r_step)
                    if self.on_step:
                        await _maybe_await(self.on_step, r_step)

                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc.get("id", ""),
                        "content": result_str,
                    })
            else:
                content = message.get("content", "")
                final = AgentStep(step_type="response", content=content)
                steps.append(final)
                if self.on_step:
                    await _maybe_await(self.on_step, final)
                return AgentResult(content=content, steps=steps, total_tokens=total_tokens, model=self.model)

        logger.warning("[%s] Max iterations reached", self.name)
        return AgentResult(
            content="Agent reached maximum iterations.",
            steps=steps, total_tokens=total_tokens, model=self.model,
        )

    async def _llm_call(self, messages: list[dict], tools: list[dict] | None = None) -> dict:
        """Raw LLM call with tool support via OpenRouter."""
        key = _next_key()
        headers = {
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://motionweaver.app",
            "X-Title": "MotionWeaver",
        }
        body: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
        }
        if tools:
            body["tools"] = tools
            body["tool_choice"] = "auto"

        try:
            client = _get_client()
            response = await client.post(OPENROUTER_URL, headers=headers, json=body, timeout=float(settings.LLM_TIMEOUT))
            if response.status_code == 401:
                _key_failures[key] = _key_failures.get(key, 0) + 1
                raise LLMError(f"API key unauthorized", status_code=401, retriable=True)
            response.raise_for_status()
            _key_failures[key] = 0
            return response.json()
        except httpx.TimeoutException:
            raise LLMError(f"Agent LLM call timed out", status_code=408, retriable=True)

    async def _execute_tool(self, tool_name: str, tool_args: dict[str, Any]) -> str:
        """Execute a registered tool."""
        tool_def = self._tool_map.get(tool_name)
        if not tool_def:
            return json.dumps({"error": f"Unknown tool: {tool_name}"})
        try:
            logger.info("[%s] Executing tool: %s", self.name, tool_name)
            result = await tool_def.handler(**tool_args)
            return result if isinstance(result, str) else json.dumps(result)
        except Exception as e:
            logger.error("[%s] Tool %s failed: %s", self.name, tool_name, e)
            return json.dumps({"error": str(e)})


async def invoke_sub_agent(
    parent_name: str, agent: Agent, prompt: str, *, context: dict[str, Any] | None = None,
) -> str:
    """Run a sub-agent and return its result content."""
    logger.info("[%s] Invoking sub-agent: %s", parent_name, agent.name)
    result = await agent.run(prompt, context=context)
    return result.content


async def _maybe_await(fn: Callable, *args: Any, **kwargs: Any) -> Any:
    result = fn(*args, **kwargs)
    if asyncio.iscoroutine(result):
        return await result
    return result
