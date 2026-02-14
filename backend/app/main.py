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

    await init_db()
    logger.info("Database initialized successfully")

    yield

    await close_db()
    logger.info("MotionWeaver shut down")


app = FastAPI(
    title="MotionWeaver API",
    description="工业级端到端漫剧创作引擎 — AI 编剧 → 本地资产生成 → 视频自动合成",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS — allow frontend dev server
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000", "*"],
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
