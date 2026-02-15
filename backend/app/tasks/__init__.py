"""Celery application configuration."""

import asyncio

from celery import Celery
from celery.schedules import crontab

from app.config import get_settings

settings = get_settings()

celery_app = Celery(
    "motionweaver",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=[
        "app.tasks.asset_tasks",
        "app.tasks.compose_task",
        "app.tasks.cleanup_task",
    ],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Asia/Shanghai",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
)

# Celery Beat schedule for cleanup — runs daily at 3:00 AM
celery_app.conf.beat_schedule = {
    "cleanup-old-media": {
        "task": "app.tasks.cleanup_task.cleanup_old_media",
        "schedule": crontab(hour=3, minute=0),
    },
}


def run_async(coro):
    """Shared helper to run async code in a sync Celery task.

    Creates a new event loop per call. All Celery tasks should use this
    instead of defining their own version.
    """
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()
