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
    task_acks_late=True,               # ACK after task completes, not on receive
    task_reject_on_worker_lost=True,    # Re-queue task if worker crashes/restarts
    worker_prefetch_multiplier=1,       # Fetch one task at a time per worker
)

# Celery Beat schedule for cleanup — runs daily at 3:00 AM
celery_app.conf.beat_schedule = {
    "cleanup-old-media": {
        "task": "app.tasks.cleanup_task.cleanup_old_media",
        "schedule": crontab(hour=3, minute=0),
    },
}

import threading

# Thread-local storage for event loop reuse within Celery workers
_thread_local = threading.local()


def run_async(coro):
    """Run async code in a sync Celery task.

    Reuses a thread-local event loop for efficiency — avoids creating
    and closing a new loop for every DB update or API call within a
    single Celery task execution.
    """
    loop = getattr(_thread_local, "loop", None)
    if loop is None or loop.is_closed():
        loop = asyncio.new_event_loop()
        _thread_local.loop = loop
    return loop.run_until_complete(coro)
