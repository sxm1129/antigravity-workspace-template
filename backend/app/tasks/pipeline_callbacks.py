from __future__ import annotations
"""Pipeline callbacks — Celery tasks triggered by chord completions."""

import logging

from celery import shared_task

from app.models.scene import SceneStatus
from app.tasks import run_async

logger = logging.getLogger(__name__)


@shared_task
def mark_scene_reviewable(results, scene_id: str, project_id: str):
    """Chord callback: mark a scene as REVIEW when audio + image are both done.

    If any sub-task returned an error result, skip — the scene stays in ERROR.
    """
    from app.services.pubsub import publish_scene_update

    # Check if any sub-task failed
    if isinstance(results, list):
        for r in results:
            if isinstance(r, dict) and r.get("status") == "error":
                logger.warning(
                    "Scene %s has failed sub-task, skipping REVIEW: %s",
                    scene_id, r,
                )
                return scene_id

    logger.info("Scene %s assets complete, marking REVIEW", scene_id)
    run_async(_update_scene_status(scene_id, SceneStatus.REVIEW.value))
    publish_scene_update(project_id, scene_id, SceneStatus.REVIEW.value)

    # Check if all scenes in project are now reviewable
    run_async(_check_all_scenes_ready(project_id))
    return scene_id


@shared_task
def compose_after_all_videos(results, project_id: str):
    """Chord callback: compose final video after all scene videos are ready.

    If any scene video failed, skip compose and log a warning.
    """
    from app.services.pubsub import publish_project_update
    from app.models.project import ProjectStatus

    # Check if any video generation failed
    failed = []
    if isinstance(results, list):
        for r in results:
            if isinstance(r, dict) and r.get("status") in ("error", "duplicate_blocked"):
                failed.append(r.get("scene_id", "unknown"))

    if failed:
        logger.warning(
            "Project %s has %d failed scene videos, skipping compose: %s",
            project_id, len(failed), failed,
        )
        publish_project_update(project_id, "COMPOSE_BLOCKED")
        return {"project_id": project_id, "status": "blocked", "failed_scenes": failed}

    logger.info("All videos ready for project %s, starting compose", project_id)

    run_async(_update_project_status(project_id, ProjectStatus.COMPOSING.value))
    publish_project_update(project_id, ProjectStatus.COMPOSING.value)

    # Trigger the compose task
    from app.tasks.compose_task import compose_project_video
    compose_project_video.delay(project_id)

    return project_id


async def _update_scene_status(scene_id: str, status: str):
    """Update scene status in DB."""
    from sqlalchemy import update
    from app.database import async_session_factory
    from app.models.scene import Scene

    async with async_session_factory() as session:
        await session.execute(
            update(Scene).where(Scene.id == scene_id).values(status=status)
        )
        await session.commit()


async def _update_project_status(project_id: str, status: str):
    """Update project status in DB."""
    from sqlalchemy import update
    from app.database import async_session_factory
    from app.models.project import Project

    async with async_session_factory() as session:
        await session.execute(
            update(Project).where(Project.id == project_id).values(status=status)
        )
        await session.commit()


async def _check_all_scenes_ready(project_id: str):
    """Check if all scenes in a project are at REVIEW or later status."""
    from sqlalchemy import select, func
    from app.database import async_session_factory
    from app.models.scene import Scene

    async with async_session_factory() as session:
        total = await session.scalar(
            select(func.count()).where(Scene.project_id == project_id)
        )
        reviewable = await session.scalar(
            select(func.count()).where(
                Scene.project_id == project_id,
                Scene.status.in_([
                    SceneStatus.REVIEW.value,
                    SceneStatus.APPROVED.value,
                    SceneStatus.READY.value,
                ])
            )
        )

    if total and total == reviewable:
        logger.info("All %d scenes in project %s are reviewable", total, project_id)
        from app.services.pubsub import publish_project_update
        from app.models.project import ProjectStatus
        publish_project_update(project_id, "ALL_SCENES_REVIEWABLE")
