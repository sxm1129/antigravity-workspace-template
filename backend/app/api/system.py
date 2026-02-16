"""System status endpoint — checks health of all dependent services."""

from __future__ import annotations

import time
from typing import Any

import redis
from fastapi import APIRouter

from app.config import get_settings
from app.tasks import celery_app

router = APIRouter()
settings = get_settings()


@router.get("/check-llm")
async def check_llm():
    """Pre-check LLM API keys — verify which keys are valid before generation."""
    from app.services.llm_client import check_llm_health
    return await check_llm_health()


def _check_redis() -> dict[str, Any]:
    """Check Redis connectivity and basic info."""
    t0 = time.time()
    try:
        r = redis.Redis.from_url(settings.REDIS_URL, socket_timeout=3)
        info = r.info("server")
        ping = r.ping()
        latency_ms = round((time.time() - t0) * 1000, 1)
        return {
            "status": "ok" if ping else "error",
            "latency_ms": latency_ms,
            "version": info.get("redis_version", "unknown"),
            "url": settings.REDIS_URL,
        }
    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
            "url": settings.REDIS_URL,
        }


def _check_celery_workers() -> dict[str, Any]:
    """Check Celery workers via ping broadcast."""
    try:
        # Ping with 2-second timeout
        inspector = celery_app.control.inspect(timeout=2)
        ping_result = inspector.ping()

        if not ping_result:
            return {
                "status": "offline",
                "workers": [],
                "count": 0,
                "message": "没有检测到运行中的 Celery Worker",
            }

        workers = []
        for worker_name, pong in ping_result.items():
            workers.append({
                "name": worker_name,
                "status": "ok" if pong.get("ok") == "pong" else "error",
            })

        # Get active tasks count
        active = inspector.active() or {}
        reserved = inspector.reserved() or {}

        total_active = sum(len(tasks) for tasks in active.values())
        total_reserved = sum(len(tasks) for tasks in reserved.values())

        # Get registered tasks
        registered = inspector.registered() or {}
        all_tasks = set()
        for tasks in registered.values():
            all_tasks.update(tasks)

        return {
            "status": "ok",
            "workers": workers,
            "count": len(workers),
            "active_tasks": total_active,
            "reserved_tasks": total_reserved,
            "registered_tasks": sorted([t for t in all_tasks if t.startswith("app.")]),
        }
    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
            "workers": [],
            "count": 0,
        }


def _check_database() -> dict[str, Any]:
    """Check database connectivity (sync, for status page)."""
    t0 = time.time()
    try:
        from sqlalchemy import create_engine, text
        from urllib.parse import quote_plus

        sync_url = (
            f"mysql+pymysql://{settings.DB_USER}:{quote_plus(settings.DB_PASSWORD)}"
            f"@{settings.DB_HOST}:{settings.DB_PORT}/{settings.DB_NAME}"
            "?charset=utf8mb4"
        )
        engine = create_engine(sync_url, pool_pre_ping=True)
        with engine.connect() as conn:
            result = conn.execute(text("SELECT 1"))
            result.fetchone()
        latency_ms = round((time.time() - t0) * 1000, 1)
        engine.dispose()
        return {
            "status": "ok",
            "latency_ms": latency_ms,
            "host": settings.DB_HOST,
            "database": settings.DB_NAME,
        }
    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
            "host": settings.DB_HOST,
            "database": settings.DB_NAME,
        }


def _check_external_api(name: str, url: str) -> dict[str, Any]:
    """Quick connectivity check for external API (DNS + TCP only)."""
    import urllib.parse
    import socket

    t0 = time.time()
    try:
        parsed = urllib.parse.urlparse(url)
        host = parsed.hostname
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        sock = socket.create_connection((host, port), timeout=3)
        sock.close()
        latency_ms = round((time.time() - t0) * 1000, 1)
        return {
            "name": name,
            "status": "ok",
            "latency_ms": latency_ms,
            "endpoint": url,
        }
    except Exception as e:
        return {
            "name": name,
            "status": "error",
            "error": str(e),
            "endpoint": url,
        }


def _check_celery_queue() -> dict[str, Any]:
    """Check Celery queue length in Redis."""
    try:
        r = redis.Redis.from_url(settings.REDIS_URL, socket_timeout=3)
        queue_length = r.llen("celery")
        return {
            "queue_name": "celery",
            "pending_tasks": queue_length,
        }
    except Exception as e:
        return {
            "queue_name": "celery",
            "pending_tasks": -1,
            "error": str(e),
        }


@router.post("/celery/start")
async def start_celery_worker():
    """Start a Celery worker process."""
    import subprocess
    import os
    import sys

    try:
        # Check if workers are already running
        inspector = celery_app.control.inspect(timeout=2)
        ping_result = inspector.ping()
        if ping_result and len(ping_result) > 0:
            return {
                "status": "already_running",
                "message": f"已有 {len(ping_result)} 个 Worker 在运行中",
                "workers": list(ping_result.keys()),
            }
    except Exception:
        pass

    try:
        # Determine the project root (backend dir)
        backend_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

        # Check if venv exists
        venv_python = os.path.join(backend_dir, "venv", "bin", "python")
        if not os.path.exists(venv_python):
            venv_python = sys.executable

        venv_celery = os.path.join(backend_dir, "venv", "bin", "celery")
        if not os.path.exists(venv_celery):
            venv_celery = "celery"

        # Start celery worker as background process
        log_file = "/tmp/mw_celery.log"
        log_fh = open(log_file, "a")
        proc = subprocess.Popen(
            [
                venv_celery,
                "-A", "app.tasks",
                "worker",
                "--loglevel=info",
                "--concurrency=2",
            ],
            cwd=backend_dir,
            stdout=log_fh,
            stderr=subprocess.STDOUT,
            start_new_session=True,  # detach from parent
        )
        log_fh.close()  # Popen has dup'd the fd; safe to close ours

        return {
            "status": "started",
            "message": f"Celery Worker 已启动 (PID: {proc.pid})",
            "pid": proc.pid,
            "log_file": log_file,
        }
    except Exception as e:
        return {
            "status": "error",
            "message": f"启动失败: {str(e)}",
        }


@router.post("/celery/stop")
async def stop_celery_worker():
    """Stop all Celery workers gracefully."""
    try:
        # Check if workers exist first
        inspector = celery_app.control.inspect(timeout=2)
        ping_result = inspector.ping()
        if not ping_result:
            return {
                "status": "no_workers",
                "message": "没有运行中的 Worker 需要停止",
            }

        worker_names = list(ping_result.keys())

        # Broadcast shutdown to all workers
        celery_app.control.broadcast("shutdown")

        return {
            "status": "stopping",
            "message": f"已向 {len(worker_names)} 个 Worker 发送停止信号",
            "workers": worker_names,
        }
    except Exception as e:
        return {
            "status": "error",
            "message": f"停止失败: {str(e)}",
        }


@router.get("/celery/logs")
async def celery_logs():
    """Get recent Celery worker logs."""
    import os

    log_file = "/tmp/mw_celery.log"
    try:
        if not os.path.exists(log_file):
            return {"logs": "", "message": "日志文件不存在"}

        with open(log_file, "r") as f:
            # Read last 5KB of log
            f.seek(0, 2)
            size = f.tell()
            f.seek(max(0, size - 5000))
            content = f.read()

        return {"logs": content, "size": size}
    except Exception as e:
        return {"logs": "", "error": str(e)}


@router.get("/status")
async def system_status():
    """Full system status check — services, workers, queues."""
    import concurrent.futures

    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as executor:
        redis_future = executor.submit(_check_redis)
        db_future = executor.submit(_check_database)
        celery_future = executor.submit(_check_celery_workers)
        queue_future = executor.submit(_check_celery_queue)
        openrouter_future = executor.submit(
            _check_external_api, "OpenRouter", settings.OPENROUTER_BASE_URL
        )
        tts_future = executor.submit(
            _check_external_api, "IndexTTS", settings.INDEX_TTS_URL
        )
        ark_future = executor.submit(
            _check_external_api, "Volcengine Ark", settings.ARK_ENDPOINT
        )

    redis_status = redis_future.result()
    db_status = db_future.result()
    celery_status = celery_future.result()
    queue_status = queue_future.result()
    external_apis = [
        openrouter_future.result(),
        tts_future.result(),
        ark_future.result(),
    ]

    # Overall health
    all_ok = (
        redis_status.get("status") == "ok"
        and db_status.get("status") == "ok"
        and celery_status.get("status") == "ok"
    )

    return {
        "overall": "ok" if all_ok else "degraded",
        "services": {
            "redis": redis_status,
            "database": db_status,
            "celery": celery_status,
            "queue": queue_status,
        },
        "external_apis": external_apis,
        "settings": {
            "image_providers": settings.IMAGE_PROVIDERS,
            "video_providers": settings.VIDEO_PROVIDERS,
        },
    }


# ---------------------------------------------------------------------------
# System Settings — runtime provider configuration
# ---------------------------------------------------------------------------

@router.get("/settings")
async def get_settings_api():
    """Get current system settings (provider configuration)."""
    return {
        "image_providers": settings.IMAGE_PROVIDERS,
        "video_providers": settings.VIDEO_PROVIDERS,
        "flux_api_base": settings.FLUX_API_BASE,
        "flux_model": settings.FLUX_MODEL,
        "image_model": settings.IMAGE_MODEL,
        "use_mock_api": settings.USE_MOCK_API,
    }


@router.put("/settings")
async def update_settings_api(body: dict):
    """Update system settings at runtime (no restart needed).

    Supported fields: image_providers, video_providers, use_mock_api.
    """
    allowed = {"image_providers", "video_providers", "use_mock_api"}
    updated = {}

    for key, value in body.items():
        if key not in allowed:
            continue

        attr = key.upper()
        if hasattr(settings, attr):
            # Mutate the cached singleton directly
            object.__setattr__(settings, attr, value)
            updated[key] = value

    if not updated:
        return {"status": "no_change", "message": "No valid fields provided"}

    return {"status": "ok", "updated": updated}
