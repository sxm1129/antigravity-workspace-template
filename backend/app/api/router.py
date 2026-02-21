from __future__ import annotations
"""Master API router — mounts all sub-routers."""

from fastapi import APIRouter

from app.api.projects import router as projects_router
from app.api.characters import router as characters_router
from app.api.scenes import router as scenes_router
from app.api.episodes import router as episodes_router
from app.api.story import router as story_router
from app.api.assets import router as assets_router
from app.api.test_pipeline import router as test_router
from app.api.quick_draft import router as quick_draft_router
from app.api.styles import router as styles_router
from app.api.metrics import router as metrics_router
from app.api.system import router as system_router
from app.api.render import router as render_router
from app.api.models import router as models_router
from app.api.agents import router as agents_router

api_router = APIRouter(prefix="/api", redirect_slashes=False)

api_router.include_router(projects_router, prefix="/projects", tags=["Projects"])
api_router.include_router(characters_router, prefix="/projects/{project_id}/characters", tags=["Characters"])
api_router.include_router(scenes_router, prefix="/projects/{project_id}/scenes", tags=["Scenes"])
api_router.include_router(episodes_router, tags=["Episodes"])
api_router.include_router(story_router, prefix="/story", tags=["Story AI"])
api_router.include_router(assets_router, prefix="/assets", tags=["Asset Generation"])
api_router.include_router(test_router, prefix="/test", tags=["Test Pipeline"])
api_router.include_router(quick_draft_router, tags=["Quick Draft"])
api_router.include_router(styles_router, prefix="/styles", tags=["Styles"])
api_router.include_router(metrics_router, prefix="/metrics", tags=["Metrics"])
api_router.include_router(system_router, prefix="/system", tags=["System"])
api_router.include_router(render_router, tags=["Render"])
api_router.include_router(models_router, tags=["Models"])
api_router.include_router(agents_router, tags=["AI Agents"])

