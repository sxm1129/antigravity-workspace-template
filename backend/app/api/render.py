from __future__ import annotations
"""Render API — compose provider info, preview props, and render trigger."""

import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.services.base_compose_service import get_compose_service, SceneData

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/render", tags=["render"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class ProviderInfo(BaseModel):
    provider: str
    supports_preview: bool


class PreviewPropsResponse(BaseModel):
    props: dict | None
    provider: str


class RenderRequest(BaseModel):
    title: str = ""
    episode_title: str | None = None
    bgm_path: str | None = None
    style: str = "default"


class RenderResponse(BaseModel):
    output_path: str
    provider: str
    duration_seconds: float


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/provider", response_model=ProviderInfo)
def get_provider():
    """Return current compose provider and preview support."""
    service = get_compose_service()
    return ProviderInfo(
        provider=service.provider_name,
        supports_preview=service.supports_preview(),
    )


@router.get("/preview-props/{project_id}", response_model=PreviewPropsResponse)
async def get_preview_props(project_id: str):
    """Get preview props for @remotion/player (only works with Remotion provider)."""
    from app.tasks.compose_task import _get_scene_data, _get_project_meta
    from app.tasks import run_async

    service = get_compose_service()
    if not service.supports_preview():
        return PreviewPropsResponse(props=None, provider=service.provider_name)

    scene_data = await _get_scene_data(project_id)
    project_meta = await _get_project_meta(project_id)

    props = service.get_preview_props(
        project_id,
        scene_data,
        title=project_meta.get("title", ""),
        style=project_meta.get("style_preset", "default"),
    )

    return PreviewPropsResponse(props=props, provider=service.provider_name)


@router.post("/start/{project_id}", response_model=RenderResponse)
async def start_render(project_id: str, req: RenderRequest):
    """Trigger video composition synchronously (for now)."""
    from app.tasks.compose_task import _get_scene_data

    service = get_compose_service()
    scene_data = await _get_scene_data(project_id)

    if not scene_data:
        raise HTTPException(status_code=404, detail="No ready scenes found")

    try:
        result = service.compose(
            project_id,
            scene_data,
            title=req.title,
            episode_title=req.episode_title,
            bgm_path=req.bgm_path,
            style=req.style,
        )
    except Exception as e:
        logger.error("Render failed for project %s: %s", project_id, e)
        raise HTTPException(status_code=500, detail=str(e))

    return RenderResponse(
        output_path=result.output_path,
        provider=result.provider,
        duration_seconds=result.duration_seconds,
    )
