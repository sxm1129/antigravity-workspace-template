from __future__ import annotations
"""MotionWeaver — FastAPI application entry point.

Mounts all API routes, configures CORS, serves media static files,
and initializes the database on startup.
"""

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.router import api_router
from app.api.ws import router as ws_router
from app.config import get_settings
from app.database import close_db, init_db

settings = get_settings()

# Configure logging
logging.basicConfig(
    level=logging.DEBUG if settings.DEBUG else logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: init DB on startup, close on shutdown."""
    logger.info("MotionWeaver starting up...")
    logger.info("USE_MOCK_API: %s", settings.USE_MOCK_API)
    logger.info("Database: %s@%s/%s", settings.DB_USER, settings.DB_HOST, settings.DB_NAME)

    # Ensure media_volume directory exists
    os.makedirs(settings.MEDIA_VOLUME, exist_ok=True)

    # --- Startup recovery: reset scenes stuck in transient states ---
    # When worker/backend restarts, any in-progress tasks are lost.
    # Reset transient statuses so users can re-trigger generation.
    _recover_stuck_scenes()

    logger.info("Skipping init_db (tables assumed to exist)")

    yield

    await close_db()
    logger.info("MotionWeaver shut down")


def _recover_stuck_scenes():
    """Reset scenes stuck in transient states after a restart.

    Transient states indicate a task was in-progress when the service
    stopped.  We roll them back to the last stable state so users can
    re-trigger the operation from the UI.

    Mapping:
      VIDEO_GEN  → REVIEW   (image exists, video was interrupted)
      IMAGE_GEN  → PENDING  (image generation was interrupted)
      AUDIO_GEN  → PENDING  (audio generation was interrupted)
    """
    from urllib.parse import quote_plus
    from sqlalchemy import create_engine, text

    try:
        url = (
            f"mysql+pymysql://{settings.DB_USER}:{quote_plus(settings.DB_PASSWORD)}"
            f"@{settings.DB_HOST}:{settings.DB_PORT}/{settings.DB_NAME}"
            "?charset=utf8mb4"
        )
        engine = create_engine(url, pool_pre_ping=True)

        transitions = [
            ("VIDEO_GEN", "REVIEW"),
            ("IMAGE_GEN", "PENDING"),
            ("AUDIO_GEN", "PENDING"),
            ("GENERATING", "PENDING"),
        ]

        with engine.connect() as conn:
            total_reset = 0
            for from_status, to_status in transitions:
                result = conn.execute(
                    text(f"UPDATE scenes SET status=:to_st WHERE status=:from_st"),
                    {"to_st": to_status, "from_st": from_status},
                )
                if result.rowcount > 0:
                    logger.warning(
                        "Startup recovery: reset %d scene(s) %s → %s",
                        result.rowcount, from_status, to_status,
                    )
                    total_reset += result.rowcount
            conn.commit()

        engine.dispose()

        if total_reset > 0:
            logger.info("Startup recovery: %d scene(s) recovered total", total_reset)
        else:
            logger.info("Startup recovery: no stuck scenes found")

    except Exception as e:
        logger.warning("Startup recovery failed (non-fatal): %s", e)


app = FastAPI(
    title="MotionWeaver API",
    description="工业级端到端漫剧创作引擎 — AI 编剧 → 本地资产生成 → 视频自动合成",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS — allow frontend dev server
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:9000", "http://localhost:3000", "http://127.0.0.1:9000", "http://127.0.0.1:3000", "*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount API routes
app.include_router(api_router)
app.include_router(ws_router)

# Mount media static files
os.makedirs(settings.MEDIA_VOLUME, exist_ok=True)
app.mount("/media", StaticFiles(directory=settings.MEDIA_VOLUME), name="media")


@app.get("/")
async def root():
    """Health check endpoint."""
    return {
        "service": "MotionWeaver",
        "status": "running",
        "mock_mode": settings.USE_MOCK_API,
    }


@app.get("/health")
async def health():
    """Detailed health check."""
    return {
        "status": "healthy",
        "database": settings.DB_HOST,
        "mock_mode": settings.USE_MOCK_API,
    }


@app.post("/api/migrate")
async def run_migration():
    """Temporary endpoint to add missing columns via the existing connection pool."""
    from sqlalchemy import text
    from app.database import engine

    results = []
    alters = [
        "ALTER TABLE projects ADD COLUMN mode VARCHAR(20) DEFAULT 'STANDARD'",
        "ALTER TABLE projects ADD COLUMN style_preset VARCHAR(50) DEFAULT 'default'",
        "ALTER TABLE projects ADD COLUMN draft_progress TEXT NULL",
        "ALTER TABLE projects ADD COLUMN final_video_path VARCHAR(500) NULL",
        "ALTER TABLE characters ADD COLUMN reference_image_path VARCHAR(500) NULL",
        "ALTER TABLE characters ADD COLUMN style_tags TEXT NULL",
    ]
    async with engine.begin() as conn:
        for sql in alters:
            try:
                await conn.execute(text(sql))
                results.append({"sql": sql[:60], "status": "OK"})
            except Exception as e:
                if "Duplicate column" in str(e):
                    results.append({"sql": sql[:60], "status": "SKIP (exists)"})
                else:
                    results.append({"sql": sql[:60], "status": f"FAIL: {e}"})
    return {"results": results}

