from __future__ import annotations
"""Project CRUD API endpoints."""

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.project import Project, PROJECT_STATUSES
from app.schemas.project import (
    ProjectCreate,
    ProjectRead,
    ProjectUpdate,
    ProjectStatusUpdate,
)

router = APIRouter()


@router.get("/", response_model=list[ProjectRead])
async def list_projects(db: AsyncSession = Depends(get_db)):
    """List all projects ordered by creation date (newest first)."""
    result = await db.execute(
        select(Project).order_by(Project.created_at.desc())
    )
    return result.scalars().all()


@router.post("/", response_model=ProjectRead, status_code=201)
async def create_project(data: ProjectCreate, db: AsyncSession = Depends(get_db)):
    """Create a new project in IDEATION status."""
    project = Project(
        id=uuid.uuid4().hex[:36],
        title=data.title,
        logline=data.logline,
        status="IDEATION",
    )
    db.add(project)
    await db.flush()
    await db.refresh(project)
    return project


@router.get("/{project_id}", response_model=ProjectRead)
async def get_project(project_id: str, db: AsyncSession = Depends(get_db)):
    """Get a project by ID."""
    project = await db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


@router.patch("/{project_id}", response_model=ProjectRead)
async def update_project(
    project_id: str, data: ProjectUpdate, db: AsyncSession = Depends(get_db)
):
    """Update a project's content fields."""
    project = await db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(project, key, value)

    await db.flush()
    await db.refresh(project)
    return project


@router.post("/{project_id}/advance-status", response_model=ProjectRead)
async def advance_project_status(
    project_id: str,
    data: ProjectStatusUpdate,
    db: AsyncSession = Depends(get_db),
):
    """Advance the project to the next status in the state machine.

    Enforces one-way sequential flow.
    """
    project = await db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    if not project.can_transition_to(data.target_status):
        raise HTTPException(
            status_code=400,
            detail=f"Cannot transition from {project.status} to {data.target_status}. "
                   f"Valid next status: {_next_status(project.status)}",
        )

    project.status = data.target_status
    await db.flush()
    await db.refresh(project)
    return project


@router.delete("/{project_id}", status_code=204)
async def delete_project(project_id: str, db: AsyncSession = Depends(get_db)):
    """Delete a project and all related data."""
    project = await db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    await db.delete(project)


def _next_status(current: str) -> str | None:
    """Get the next valid status in the state machine."""
    try:
        idx = PROJECT_STATUSES.index(current)
        if idx + 1 < len(PROJECT_STATUSES):
            return PROJECT_STATUSES[idx + 1]
    except ValueError:
        pass
    return None
