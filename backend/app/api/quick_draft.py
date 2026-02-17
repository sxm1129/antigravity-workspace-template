from __future__ import annotations
"""Quick Draft API — one-click preview mode."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.project import Project, ProjectMode, ProjectStatus

router = APIRouter(prefix="/quick-draft", tags=["quick-draft"])


class QuickDraftRequest(BaseModel):
    title: str
    logline: str
    style: str = "default"


@router.post("/")
@router.post("", include_in_schema=False)
async def start_quick_draft(req: QuickDraftRequest, db: AsyncSession = Depends(get_db)):
    """Create a project and immediately start the full AI pipeline."""
    import uuid

    project = Project(
        id=uuid.uuid4().hex[:36],
        title=req.title,
        logline=req.logline,
        mode=ProjectMode.QUICK_DRAFT.value,
        style_preset=req.style,
        status=ProjectStatus.DRAFT.value,
    )
    db.add(project)
    await db.flush()

    from app.tasks.quick_draft_task import run_quick_draft
    task = run_quick_draft.delay(project.id, req.logline, req.style)

    return {
        "project_id": project.id,
        "task_id": task.id,
        "status": "pipeline_started",
    }


@router.get("/{project_id}/progress")
async def get_draft_progress(project_id: str, db: AsyncSession = Depends(get_db)):
    """Poll draft progress (fallback when WebSocket unavailable)."""
    import json

    project = await db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    progress = None
    if project.draft_progress:
        try:
            progress = json.loads(project.draft_progress)
        except (json.JSONDecodeError, TypeError):
            pass

    return {
        "project_id": project_id,
        "status": project.status,
        "progress": progress,
        "final_video_path": project.final_video_path,
    }
