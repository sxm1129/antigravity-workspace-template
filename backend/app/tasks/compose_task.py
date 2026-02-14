from __future__ import annotations
"""Celery task for FFmpeg final video composition."""

import asyncio
import logging

from celery import shared_task

logger = logging.getLogger(__name__)


def _run_async(coro):
    """Helper to run async code in a sync Celery task."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@shared_task(bind=True, max_retries=1)
def compose_project_video(self, project_id: str):
    """Compose all READY scene videos into a final output for the project.

    Only triggered when ALL scenes in a project have status = READY.
    """
    try:
        # Get all scene video paths ordered by sequence
        scene_paths = _run_async(_get_scene_video_paths(project_id))

        if not scene_paths:
            logger.warning("No scene videos found for project %s", project_id)
            return {"project_id": project_id, "status": "no_videos"}

        from app.services.ffmpeg_service import compose_final_video

        output_path = compose_final_video(project_id, scene_paths)

        # Update project status to COMPLETED
        _run_async(_update_project_status(project_id, "COMPLETED"))

        logger.info("Project %s video composed: %s", project_id, output_path)
        return {"project_id": project_id, "output_path": output_path}

    except Exception as exc:
        logger.error("Video composition failed for project %s: %s", project_id, exc)
        raise self.retry(exc=exc)


async def _get_scene_video_paths(project_id: str) -> list[str]:
    """Get ordered list of scene video paths for a project."""
    from sqlalchemy import select

    from app.database import async_session_factory
    from app.models.scene import Scene

    async with async_session_factory() as session:
        result = await session.execute(
            select(Scene.local_video_path)
            .where(Scene.project_id == project_id, Scene.status == "READY")
            .order_by(Scene.sequence_order)
        )
        paths = [row[0] for row in result.fetchall() if row[0]]
        return paths


async def _update_project_status(project_id: str, status: str) -> None:
    """Update project status."""
    from sqlalchemy import update

    from app.database import async_session_factory
    from app.models.project import Project

    async with async_session_factory() as session:
        await session.execute(
            update(Project).where(Project.id == project_id).values(status=status)
        )
        await session.commit()
