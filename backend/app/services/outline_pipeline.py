"""OutlinePipeline — orchestrates multi-agent outline generation.

Runs 4 agents in strict serial order, yielding SSE-compatible events
after each step to enable real-time progress display and user intervention.
"""

from __future__ import annotations

import logging
from typing import Any, AsyncGenerator

from .agents.base import (
    IntentResult,
    WorldResult,
    PlotResult,
    PipelineEvent,
)
from .agents.intent_agent import IntentAgent
from .agents.world_agent import WorldBuildingAgent
from .agents.plot_agent import PlotAgent
from .agents.assembler_agent import AssemblerAgent

logger = logging.getLogger(__name__)

# Agent step definitions (order matters — strict serial)
STEPS = [
    {"key": "intent", "index": 0, "label": "意图识别"},
    {"key": "world",  "index": 1, "label": "世界观 & 角色构建"},
    {"key": "plot",   "index": 2, "label": "剧情架构"},
    {"key": "assemble", "index": 3, "label": "组装大纲"},
]


class OutlinePipeline:
    """Orchestrates the 4-agent outline generation pipeline.

    Usage:
        pipeline = OutlinePipeline()
        async for event in pipeline.run(logline, style):
            # event is a PipelineEvent — send via SSE
            ...
    """

    def __init__(self) -> None:
        self.intent_agent = IntentAgent()
        self.world_agent = WorldBuildingAgent()
        self.plot_agent = PlotAgent()
        self.assembler_agent = AssemblerAgent()

    async def run(
        self,
        logline: str,
        style: str = "default",
        *,
        # Allow resuming from a specific step with pre-existing results
        start_from: int = 0,
        prior_intent: dict | None = None,
        prior_world: dict | None = None,
        prior_plot: dict | None = None,
    ) -> AsyncGenerator[PipelineEvent, None]:
        """Run the pipeline, yielding events for each step.

        Args:
            logline: The user's story idea.
            style: Style preset name.
            start_from: Step index to start from (0-3). Used for continue-pipeline.
            prior_intent: Pre-existing IntentResult (if resuming from step > 0).
            prior_world: Pre-existing WorldResult (if resuming from step > 1).
            prior_plot: Pre-existing PlotResult (if resuming from step > 2).
        """
        # Reconstruct prior results if resuming
        intent: IntentResult | None = IntentResult(**prior_intent) if prior_intent else None
        world: WorldResult | None = WorldResult(**prior_world) if prior_world else None
        plot: PlotResult | None = PlotResult(**prior_plot) if prior_plot else None

        current_step = "init"
        try:
            # Step 0: Intent
            if start_from <= 0:
                current_step = "intent"
                yield self._step_start("intent")
                intent = await self.intent_agent.run(logline, style)
                yield self._step_complete("intent", intent.model_dump())

            # Step 1: World Building
            if start_from <= 1:
                current_step = "world"
                yield self._step_start("world")
                world = await self.world_agent.run(logline, style, intent=intent)
                yield self._step_complete("world", world.model_dump())

            # Step 2: Plot
            if start_from <= 2:
                current_step = "plot"
                yield self._step_start("plot")
                plot = await self.plot_agent.run(logline, style, intent=intent, world=world)
                yield self._step_complete("plot", plot.model_dump())

            # Step 3: Assemble
            current_step = "assemble"
            yield self._step_start("assemble")
            outline: str = await self.assembler_agent.run(
                logline, style, intent=intent, world=world, plot=plot,
            )
            preview = outline[:200] if isinstance(outline, str) else ""
            yield self._step_complete("assemble", {"outline_preview": preview})

            # Pipeline complete
            yield PipelineEvent(
                event_type="pipeline_complete",
                outline=outline if isinstance(outline, str) else "",
            )

        except Exception as e:
            logger.exception("Pipeline error at step '%s'", current_step)
            yield PipelineEvent(
                event_type="error",
                step=current_step,
                error=f"[{current_step}] {e}",
            )

    def _step_start(self, step_key: str) -> PipelineEvent:
        step = next(s for s in STEPS if s["key"] == step_key)
        logger.info("Pipeline step START: %s (%s)", step_key, step["label"])
        return PipelineEvent(
            event_type="step_start",
            step=step_key,
            label=step["label"],
            index=step["index"],
        )

    def _step_complete(self, step_key: str, result: dict) -> PipelineEvent:
        step = next(s for s in STEPS if s["key"] == step_key)
        logger.info("Pipeline step COMPLETE: %s", step_key)
        return PipelineEvent(
            event_type="step_complete",
            step=step_key,
            label=step["label"],
            index=step["index"],
            result=result,
        )
