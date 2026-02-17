from __future__ import annotations
"""Celery task for final video composition (FFmpeg or Remotion)."""

import logging

from celery import shared_task

from app.models.project import ProjectStatus
from app.tasks import run_async

logger = logging.getLogger(__name__)


@shared_task(time_limit=600, soft_time_limit=480)
def compose_project_video(project_id: str, episode_id: str | None = None):
    """Compose READY scene videos into a final output.

    Uses the configured compose provider (ffmpeg or remotion) via Strategy Pattern.
    If episode_id is provided, only scenes from that episode are composed.
    """
    try:
        # Build SceneData list from database
        scene_data_list = run_async(_get_scene_data(project_id, episode_id=episode_id))

        if not scene_data_list:
            logger.warning("No scene videos found for project %s", project_id)
            return {"project_id": project_id, "status": "no_videos"}

        # Get project metadata for title card
        project_meta = run_async(_get_project_meta(project_id))

        from app.services.base_compose_service import get_compose_service

        service = get_compose_service()

        # Throttled progress callback — broadcast to WS every 5%
        last_pct = [-1]  # mutable container for closure

        def _on_progress(rendered: int, total: int) -> None:
            pct = round(rendered / total * 100) if total > 0 else 0
            if pct - last_pct[0] >= 5 or pct >= 100:
                last_pct[0] = pct
                try:
                    from app.services.pubsub import publish_compose_progress
                    publish_compose_progress(project_id, rendered, total)
                except Exception:
                    pass

        result = service.compose(
            project_id,
            scene_data_list,
            title=project_meta.get("title", ""),
            style=project_meta.get("style_preset", "default"),
            on_progress=_on_progress,
        )

        # Update project status to COMPLETED and save final video path
        run_async(_update_project_status(
            project_id,
            ProjectStatus.COMPLETED.value,
            final_video_path=result.output_path,
        ))

        # Update episode status if episode-level compose
        if episode_id:
            run_async(_update_episode_status(episode_id, "COMPLETED", result.output_path))

        # Broadcast project completion via WebSocket
        run_async(_broadcast_project_update(project_id, ProjectStatus.COMPLETED.value))

        logger.info(
            "Project %s video composed via %s: %s",
            project_id, result.provider, result.output_path,
        )
        return {"project_id": project_id, "output_path": result.output_path, "provider": result.provider}

    except Exception as exc:
        logger.error("Video composition failed for project %s: %s", project_id, exc)
        # Roll back status to PRODUCTION so user can inspect and retry
        try:
            run_async(_update_project_status(project_id, ProjectStatus.PRODUCTION.value))
            run_async(_broadcast_project_update(project_id, ProjectStatus.PRODUCTION.value))
            logger.info("Project %s rolled back to PRODUCTION after compose failure", project_id)
        except Exception as rollback_err:
            logger.error("Failed to rollback project %s status: %s", project_id, rollback_err)
        return {"project_id": project_id, "status": "failed", "error": str(exc)}


async def _get_scene_data(project_id: str, episode_id: str | None = None) -> list:
    """Build SceneData list from READY scenes, optionally filtered by episode."""
    from sqlalchemy import select

    from app.database import async_session_factory
    from app.models.scene import Scene, SceneStatus
    from app.services.base_compose_service import SceneData

    async with async_session_factory() as session:
        query = (
            select(Scene)
            .where(Scene.project_id == project_id, Scene.status == SceneStatus.READY.value)
        )
        if episode_id:
            query = query.where(Scene.episode_id == episode_id)
        query = query.order_by(Scene.sequence_order)

        result = await session.execute(query)
        scenes = result.scalars().all()
        return [
            SceneData(
                id=s.id,
                video_path=s.local_video_path or "",
                audio_path=s.local_audio_path,
                dialogue_text=s.dialogue_text,
                sfx_text=s.sfx_text,
                prompt_motion=s.prompt_motion,
                sequence_order=s.sequence_order,
            )
            for s in scenes
            if s.local_video_path
        ]


async def _get_project_meta(project_id: str) -> dict:
    """Get project title and style for compose metadata."""
    from app.database import async_session_factory
    from app.models.project import Project

    async with async_session_factory() as session:
        project = await session.get(Project, project_id)
        if not project:
            return {}
        return {
            "title": project.title or "",
            "style_preset": project.style_preset or "default",
        }


async def _update_project_status(project_id: str, status: str, final_video_path: str | None = None) -> None:
    """Update project status and optionally save final_video_path."""
    from sqlalchemy import update

    from app.database import async_session_factory
    from app.models.project import Project

    values: dict = {"status": status}
    if final_video_path is not None:
        values["final_video_path"] = final_video_path

    async with async_session_factory() as session:
        await session.execute(
            update(Project).where(Project.id == project_id).values(**values)
        )
        await session.commit()


async def _broadcast_project_update(project_id: str, status: str) -> None:
    """Publish project status update via Redis Pub/Sub (sync-safe wrapper)."""
    try:
        from app.services.pubsub import publish_project_update
        publish_project_update(project_id, status)
    except Exception:
        pass


async def _update_episode_status(episode_id: str, status: str, final_video_path: str | None = None) -> None:
    """Update episode status and optionally save final_video_path."""
    from sqlalchemy import update

    from app.database import async_session_factory
    from app.models.episode import Episode

    values: dict = {"status": status}
    if final_video_path is not None:
        values["final_video_path"] = final_video_path

    async with async_session_factory() as session:
        await session.execute(
            update(Episode).where(Episode.id == episode_id).values(**values)
        )
        await session.commit()
