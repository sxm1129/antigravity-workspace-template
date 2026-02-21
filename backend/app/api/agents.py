"""Agent API endpoints — invoke AI agents for content generation."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.services.agents.storyboard_agent import generate_storyboard
from app.services.agents.outline_agent import generate_full_outline
from app.services.agents.prompt_agent import polish_prompt

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/agents", tags=["AI Agents"])


class StoryboardRequest(BaseModel):
    script: str = Field(..., description="Script text to generate storyboard from")
    style: str = Field("cinematic anime", description="Visual style")
    model: str | None = Field(None, description="Override LLM model")


class OutlineRequest(BaseModel):
    logline: str = Field(..., description="Story premise / logline")
    num_episodes: int = Field(5, ge=1, le=30, description="Number of episodes")
    model: str | None = Field(None, description="Override LLM model")


class PromptPolishRequest(BaseModel):
    description: str = Field(..., description="Scene description to enhance")
    style: str = Field("cinematic anime", description="Visual style")
    character_descriptions: str | None = Field(None, description="Character appearance info")
    include_motion: bool = Field(False, description="Also generate motion prompt")
    model: str | None = Field(None, description="Override LLM model")


class AgentResponse(BaseModel):
    content: str
    steps_count: int
    total_tokens: int
    model: str


@router.post("/storyboard", response_model=AgentResponse)
async def api_generate_storyboard(req: StoryboardRequest) -> AgentResponse:
    """Generate a storyboard from a script using the Storyboard Agent."""
    try:
        result = await generate_storyboard(
            req.script, style=req.style, model=req.model,
        )
        return AgentResponse(
            content=result.content,
            steps_count=len(result.steps),
            total_tokens=result.total_tokens,
            model=result.model,
        )
    except Exception as e:
        logger.error("Storyboard agent failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/outline", response_model=AgentResponse)
async def api_generate_outline(req: OutlineRequest) -> AgentResponse:
    """Generate a full outline from a logline using the Outline Agent."""
    try:
        result = await generate_full_outline(
            req.logline, num_episodes=req.num_episodes, model=req.model,
        )
        return AgentResponse(
            content=result.content,
            steps_count=len(result.steps),
            total_tokens=result.total_tokens,
            model=result.model,
        )
    except Exception as e:
        logger.error("Outline agent failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/polish-prompt", response_model=AgentResponse)
async def api_polish_prompt(req: PromptPolishRequest) -> AgentResponse:
    """Polish a scene description into optimized AI generation prompts."""
    try:
        result = await polish_prompt(
            req.description,
            style=req.style,
            character_descriptions=req.character_descriptions,
            include_motion=req.include_motion,
            model=req.model,
        )
        return AgentResponse(
            content=result.content,
            steps_count=len(result.steps),
            total_tokens=result.total_tokens,
            model=result.model,
        )
    except Exception as e:
        logger.error("Prompt agent failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))
