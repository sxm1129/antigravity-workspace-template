from __future__ import annotations
"""Celery Beat task for disk cleanup — runs daily at 3 AM.

Scans media_volume for COMPLETED projects older than 3 days.
Deletes all intermediate files, keeping only final_output.mp4.
"""

import asyncio
import logging
import os
import shutil
from datetime import datetime, timedelta

from celery import shared_task

from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


def _run_async(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@shared_task
def cleanup_old_media():
    """Delete intermediate media files for old COMPLETED projects.

    Keeps only final_output.mp4 for completed projects.
    Deletes audio/, images/, videos/ subdirectories.
    """
    completed_projects = _run_async(_get_old_completed_projects())

    cleaned_count = 0
    freed_bytes = 0

    for proj_id in completed_projects:
        proj_dir = os.path.join(settings.MEDIA_VOLUME, proj_id)
        if not os.path.isdir(proj_dir):
            continue

        # Remove intermediate directories
        for subdir in ["audio", "images", "videos"]:
            subdir_path = os.path.join(proj_dir, subdir)
            if os.path.isdir(subdir_path):
                dir_size = _get_dir_size(subdir_path)
                shutil.rmtree(subdir_path, ignore_errors=True)
                freed_bytes += dir_size
                logger.info("Cleaned %s (%d bytes)", subdir_path, dir_size)

        # Also remove any _norm_*.mp4 leftovers
        for f in os.listdir(proj_dir):
            if f.startswith("_norm_") and f.endswith(".mp4"):
                fpath = os.path.join(proj_dir, f)
                freed_bytes += os.path.getsize(fpath)
                os.remove(fpath)

        cleaned_count += 1

    logger.info(
        "Cleanup complete: %d projects, %.2f MB freed",
        cleaned_count,
        freed_bytes / (1024 * 1024),
    )
    return {"cleaned": cleaned_count, "freed_mb": round(freed_bytes / (1024 * 1024), 2)}


async def _get_old_completed_projects() -> list[str]:
    """Get project IDs that are COMPLETED and updated > 3 days ago."""
    from sqlalchemy import select

    from app.database import async_session_factory
    from app.models.project import Project

    cutoff = datetime.utcnow() - timedelta(days=3)

    async with async_session_factory() as session:
        result = await session.execute(
            select(Project.id).where(
                Project.status == "COMPLETED",
                Project.updated_at < cutoff,
            )
        )
        return [row[0] for row in result.fetchall()]


def _get_dir_size(path: str) -> int:
    """Calculate total size of a directory."""
    total = 0
    for dirpath, _, filenames in os.walk(path):
        for f in filenames:
            fp = os.path.join(dirpath, f)
            try:
                total += os.path.getsize(fp)
            except OSError:
                pass
    return total
