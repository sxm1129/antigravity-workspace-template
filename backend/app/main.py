from __future__ import annotations
"""MotionWeaver — FastAPI application entry point.

Mounts all API routes, configures CORS, serves media static files,
and initializes the database on startup.
"""

import asyncio
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
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
    await asyncio.to_thread(_recover_stuck_scenes)

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
            ("VIDEO_GEN", "REVIEW"),     # image exists, video interrupted → show for re-approval
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

            # --- Recover stuck episodes (COMPOSING → PRODUCTION) ---
            result = conn.execute(
                text("UPDATE episodes SET status=:to_st WHERE status=:from_st"),
                {"to_st": "PRODUCTION", "from_st": "COMPOSING"},
            )
            if result.rowcount > 0:
                logger.warning(
                    "Startup recovery: reset %d episode(s) COMPOSING → PRODUCTION",
                    result.rowcount,
                )
                total_reset += result.rowcount

            # --- Recover stuck projects (COMPOSING → PRODUCTION) ---
            result = conn.execute(
                text("UPDATE projects SET status=:to_st WHERE status=:from_st"),
                {"to_st": "PRODUCTION", "from_st": "COMPOSING"},
            )
            if result.rowcount > 0:
                logger.warning(
                    "Startup recovery: reset %d project(s) COMPOSING → PRODUCTION",
                    result.rowcount,
                )
                total_reset += result.rowcount

            conn.commit()

        engine.dispose()

        if total_reset > 0:
            logger.info("Startup recovery: %d item(s) recovered total", total_reset)
        else:
            logger.info("Startup recovery: no stuck items found")

    except Exception as e:
        logger.warning("Startup recovery failed (non-fatal): %s", e)


app = FastAPI(
    title="MotionWeaver API",
    description="工业级端到端漫剧创作引擎 — AI 编剧 → 本地资产生成 → 视频自动合成",
    version="0.1.0",
    lifespan=lifespan,
    redirect_slashes=False,
)

# CORS — allow frontend dev server (configurable via CORS_ORIGINS env)
_cors_origins = os.environ.get(
    "CORS_ORIGINS",
    "http://localhost:9000,http://localhost:3000,http://127.0.0.1:9000,http://127.0.0.1:3000",
).split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
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
    """Add missing columns via the existing connection pool. Only available in DEBUG mode."""
    if not settings.DEBUG:
        raise HTTPException(status_code=403, detail="Migration endpoint disabled in production")

    from sqlalchemy import text
    from app.database import engine

    results = []
    async with engine.begin() as conn:
        # -- Step 1: Create episodes table if missing --
        create_episodes = """
        CREATE TABLE IF NOT EXISTS episodes (
            id VARCHAR(36) PRIMARY KEY,
            project_id VARCHAR(36) NOT NULL,
            episode_number INT NOT NULL DEFAULT 1,
            title VARCHAR(255) NOT NULL DEFAULT '',
            synopsis LONGTEXT NULL,
            full_script LONGTEXT NULL,
            final_video_path VARCHAR(1024) NULL,
            status VARCHAR(50) NOT NULL DEFAULT 'SCRIPT_GENERATING',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            INDEX idx_ep_project (project_id),
            FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """
        try:
            await conn.execute(text(create_episodes))
            results.append({"sql": "CREATE TABLE episodes", "status": "OK"})
        except Exception as e:
            results.append({"sql": "CREATE TABLE episodes", "status": f"SKIP: {e}"})

        # -- Step 2: ALTER TABLE additions --
        alters = [
            "ALTER TABLE projects ADD COLUMN mode VARCHAR(20) DEFAULT 'STANDARD'",
            "ALTER TABLE projects ADD COLUMN style_preset VARCHAR(50) DEFAULT 'default'",
            "ALTER TABLE projects ADD COLUMN draft_progress TEXT NULL",
            "ALTER TABLE projects ADD COLUMN final_video_path VARCHAR(500) NULL",
            "ALTER TABLE characters ADD COLUMN reference_image_path VARCHAR(500) NULL",
            "ALTER TABLE characters ADD COLUMN style_tags TEXT NULL",
            "ALTER TABLE scenes ADD COLUMN episode_id VARCHAR(36) NULL",
        ]
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


