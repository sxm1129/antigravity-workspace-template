from __future__ import annotations
"""Master API router — mounts all sub-routers."""

from fastapi import APIRouter

from app.api.projects import router as projects_router
from app.api.characters import router as characters_router
from app.api.scenes import router as scenes_router
from app.api.story import router as story_router
from app.api.assets import router as assets_router

api_router = APIRouter(prefix="/api")

api_router.include_router(projects_router, prefix="/projects", tags=["Projects"])
api_router.include_router(characters_router, prefix="/projects/{project_id}/characters", tags=["Characters"])
api_router.include_router(scenes_router, prefix="/projects/{project_id}/scenes", tags=["Scenes"])
api_router.include_router(story_router, prefix="/story", tags=["Story AI"])
api_router.include_router(assets_router, prefix="/assets", tags=["Asset Generation"])
