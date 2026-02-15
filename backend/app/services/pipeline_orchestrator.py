from __future__ import annotations
"""Pipeline orchestrator — builds Celery DAGs for production workflows."""

import logging
from typing import Any

from celery import chain, chord, group

logger = logging.getLogger(__name__)


def build_production_pipeline(project_id: str, scenes: list[dict[str, Any]]):
    """Build a Celery DAG for parallel scene asset generation.

    For each scene:
      - audio and image generation run in parallel (group)
      - when both complete, a callback marks the scene as REVIEW (chord)

    All scenes run in parallel.
    """
    from app.tasks.asset_tasks import generate_scene_audio, generate_scene_image
    from app.tasks.pipeline_callbacks import mark_scene_reviewable

    scene_pipelines = []
    for scene in scenes:
        sid = scene["id"]
        pid = project_id

        asset_group = group(
            generate_scene_audio.s(
                sid, pid, scene.get("dialogue_text", ""),
            ),
            generate_scene_image.s(
                sid, pid, scene.get("prompt_visual", ""),
                scene.get("sfx_text"),
                scene.get("identity_refs"),
            ),
        )

        # chord: run assets in parallel, then mark reviewable
        scene_chord = chord(asset_group, mark_scene_reviewable.s(sid, pid))
        scene_pipelines.append(scene_chord)

    return group(scene_pipelines)


def build_video_pipeline(project_id: str, approved_scenes: list[dict[str, Any]]):
    """Build a Celery DAG: generate all scene videos → compose final.

    All approved scenes generate video in parallel.
    When all complete, compose the final video.
    """
    from app.tasks.asset_tasks import generate_scene_video
    from app.tasks.pipeline_callbacks import compose_after_all_videos

    video_tasks = group(
        generate_scene_video.s(
            scene["id"],
            project_id,
            scene.get("prompt_motion", ""),
            scene.get("local_image_path", ""),
            scene.get("local_audio_path"),
        )
        for scene in approved_scenes
    )

    return chord(video_tasks, compose_after_all_videos.s(project_id))
