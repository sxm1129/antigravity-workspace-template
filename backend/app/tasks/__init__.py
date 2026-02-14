"""Celery application configuration."""

from celery import Celery

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

# Celery Beat schedule for cleanup
celery_app.conf.beat_schedule = {
    "cleanup-old-media": {
        "task": "app.tasks.cleanup_task.cleanup_old_media",
        "schedule": {
            # Every day at 3:00 AM
            "hour": 3,
            "minute": 0,
        },
    },
}
