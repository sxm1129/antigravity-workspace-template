"""Novel import API — upload, parse, adapt, and link novels."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.database import get_db
from app.services import novel_import

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/novels", tags=["Novels"])


# ---------------------------------------------------------------------------
# Request / Response schemas
# ---------------------------------------------------------------------------

class NovelUploadRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=255, description="Novel title")
    raw_text: str = Field(..., min_length=100, max_length=5_000_000, description="Full novel text content (max 5MB)")
    author: str | None = Field(None, max_length=255, description="Author name")
    genre: str | None = Field(None, max_length=100, description="Genre")


class NovelResponse(BaseModel):
    id: str
    title: str
    author: str | None = None
    genre: str | None = None
    total_chapters: int
    total_words: int
    status: str
    project_id: str | None = None


class ChapterResponse(BaseModel):
    chapter_number: int
    title: str | None = None
    word_count: int
    summary: str | None = None
    has_script: bool


class AdaptRequest(BaseModel):
    style: str = Field("cinematic anime", description="Visual style")
    max_chapters: int | None = Field(None, description="Max chapters to adapt")


class LinkRequest(BaseModel):
    project_id: str = Field(..., description="Project ID to link to")


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("", response_model=NovelResponse)
async def upload_novel(req: NovelUploadRequest, db=Depends(get_db)):
    """Upload a novel for adaptation."""
    novel = await novel_import.create_novel(
        db, title=req.title, raw_text=req.raw_text,
        author=req.author, genre=req.genre,
    )
    return _novel_to_response(novel)


@router.get("", response_model=list[NovelResponse])
async def list_novels(db=Depends(get_db)):
    """List all imported novels."""
    novels = await novel_import.list_novels(db)
    return [_novel_to_response(n) for n in novels]


@router.get("/{novel_id}", response_model=NovelResponse)
async def get_novel(novel_id: str, db=Depends(get_db)):
    """Get novel details."""
    novel = await novel_import.get_novel(db, novel_id)
    if not novel:
        raise HTTPException(status_code=404, detail="Novel not found")
    return _novel_to_response(novel)


@router.post("/{novel_id}/parse", response_model=NovelResponse)
async def parse_novel(novel_id: str, db=Depends(get_db)):
    """Parse a novel's raw text into chapters."""
    try:
        novel = await novel_import.parse_novel(db, novel_id)
        return _novel_to_response(novel)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.get("/{novel_id}/chapters", response_model=list[ChapterResponse])
async def list_chapters(novel_id: str, db=Depends(get_db)):
    """List chapters of a novel."""
    from sqlalchemy import select
    from app.models.novel import NovelChapter

    result = await db.execute(
        select(NovelChapter)
        .where(NovelChapter.novel_id == novel_id)
        .order_by(NovelChapter.chapter_number)
    )
    chapters = result.scalars().all()
    return [
        ChapterResponse(
            chapter_number=ch.chapter_number,
            title=ch.title,
            word_count=ch.word_count,
            summary=ch.summary,
            has_script=bool(ch.adapted_script),
        )
        for ch in chapters
    ]


@router.post("/{novel_id}/adapt", response_model=NovelResponse)
async def adapt_novel(novel_id: str, req: AdaptRequest, db=Depends(get_db)):
    """Adapt all chapters to drama scripts using AI agents."""
    try:
        novel = await novel_import.adapt_novel(
            db, novel_id, style=req.style, max_chapters=req.max_chapters,
        )
        return _novel_to_response(novel)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/{novel_id}/link", response_model=NovelResponse)
async def link_novel(novel_id: str, req: LinkRequest, db=Depends(get_db)):
    """Link an adapted novel to a project."""
    try:
        novel = await novel_import.link_to_project(db, novel_id, req.project_id)
        return _novel_to_response(novel)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


def _novel_to_response(novel) -> NovelResponse:
    return NovelResponse(
        id=novel.id,
        title=novel.title,
        author=novel.author,
        genre=novel.genre,
        total_chapters=novel.total_chapters,
        total_words=novel.total_words,
        status=novel.status,
        project_id=novel.project_id,
    )
