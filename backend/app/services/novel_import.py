"""Novel import and adaptation service.

Pipeline:
1. Upload: Accept raw text / txt file → store in Novel
2. Parse: Split into chapters using regex or LLM
3. Adapt: Convert chapters to scripts using OutlineAgent + PromptAgent
4. Link: Create a Project from adapted novel
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.novel import Novel, NovelChapter, NovelStatus

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Chapter parsing
# ---------------------------------------------------------------------------

_CHAPTER_PATTERNS = [
    # Chinese: 第X章, 第X节, 第X回
    re.compile(r"(第[一二三四五六七八九十百千\d]+[章节回])[^\n]*", re.MULTILINE),
    # English: Chapter X, CHAPTER X
    re.compile(r"(Chapter\s+\d+)[^\n]*", re.IGNORECASE | re.MULTILINE),
    # Numbered: 1., 2., etc. at line start
    re.compile(r"^(\d+)\.\s+[^\n]+", re.MULTILINE),
]


def parse_chapters(raw_text: str) -> list[dict[str, Any]]:
    """Split raw novel text into chapters.

    Returns list of dicts: {chapter_number, title, content, word_count}
    """
    chapters: list[dict[str, Any]] = []

    # Try each pattern
    for pattern in _CHAPTER_PATTERNS:
        matches = list(pattern.finditer(raw_text))
        if len(matches) >= 2:  # Need at least 2 chapter markers
            for i, match in enumerate(matches):
                start = match.start()
                end = matches[i + 1].start() if i + 1 < len(matches) else len(raw_text)
                content = raw_text[start:end].strip()
                title = match.group(0).strip()

                chapters.append({
                    "chapter_number": i + 1,
                    "title": title,
                    "content": content,
                    "word_count": len(content),
                })
            break

    # Fallback: split by double newlines and group into ~2000 char chunks
    if not chapters:
        paragraphs = re.split(r"\n{2,}", raw_text.strip())
        chunk = ""
        num = 1
        for para in paragraphs:
            chunk += para + "\n\n"
            if len(chunk) >= 2000:
                chapters.append({
                    "chapter_number": num,
                    "title": f"Segment {num}",
                    "content": chunk.strip(),
                    "word_count": len(chunk),
                })
                chunk = ""
                num += 1
        if chunk.strip():
            chapters.append({
                "chapter_number": num,
                "title": f"Segment {num}",
                "content": chunk.strip(),
                "word_count": len(chunk),
            })

    return chapters


# ---------------------------------------------------------------------------
# Service functions
# ---------------------------------------------------------------------------

async def create_novel(
    db: AsyncSession,
    *,
    title: str,
    raw_text: str,
    author: str | None = None,
    genre: str | None = None,
) -> Novel:
    """Upload and create a novel record."""
    novel = Novel(
        title=title,
        author=author,
        genre=genre,
        raw_text=raw_text,
        total_words=len(raw_text),
        status=NovelStatus.UPLOADED.value,
    )
    db.add(novel)
    await db.commit()
    await db.refresh(novel)
    logger.info("Novel created: id=%s title=%s words=%d", novel.id, title, len(raw_text))
    return novel


async def parse_novel(db: AsyncSession, novel_id: str) -> Novel:
    """Parse a novel's raw text into chapters."""
    result = await db.execute(select(Novel).where(Novel.id == novel_id))
    novel = result.scalar_one_or_none()
    if not novel:
        raise ValueError(f"Novel not found: {novel_id}")

    novel.status = NovelStatus.PARSING.value
    await db.commit()

    chapters_data = parse_chapters(novel.raw_text or "")
    if not chapters_data:
        raise RuntimeError("Failed to parse any chapters from the novel text")

    # Create chapter records
    for ch_data in chapters_data:
        chapter = NovelChapter(
            novel_id=novel_id,
            chapter_number=ch_data["chapter_number"],
            title=ch_data["title"],
            content=ch_data["content"],
            word_count=ch_data["word_count"],
        )
        db.add(chapter)

    novel.total_chapters = len(chapters_data)
    novel.status = NovelStatus.PARSED.value
    await db.commit()
    await db.refresh(novel)

    logger.info("Novel parsed: id=%s chapters=%d", novel_id, len(chapters_data))
    return novel


async def adapt_chapter(
    db: AsyncSession,
    novel_id: str,
    chapter_number: int,
    *,
    style: str = "cinematic anime",
) -> NovelChapter:
    """Adapt a single chapter to a drama script using AI agents."""
    from app.services.agents.outline_agent import generate_full_outline
    from app.services.agents.prompt_agent import polish_prompt

    result = await db.execute(
        select(NovelChapter)
        .where(NovelChapter.novel_id == novel_id, NovelChapter.chapter_number == chapter_number)
    )
    chapter = result.scalar_one_or_none()
    if not chapter:
        raise ValueError(f"Chapter {chapter_number} not found in novel {novel_id}")

    # Generate outline from chapter content
    outline_result = await generate_full_outline(
        chapter.content or "",
        num_episodes=1,
    )

    # Store summary and adapted script
    chapter.summary = outline_result.content[:2000]
    chapter.adapted_script = outline_result.content
    await db.commit()
    await db.refresh(chapter)

    logger.info("Chapter %d adapted for novel %s", chapter_number, novel_id)
    return chapter


async def adapt_novel(
    db: AsyncSession,
    novel_id: str,
    *,
    style: str = "cinematic anime",
    max_chapters: int | None = None,
) -> Novel:
    """Adapt all chapters of a novel."""
    result = await db.execute(select(Novel).where(Novel.id == novel_id))
    novel = result.scalar_one_or_none()
    if not novel:
        raise ValueError(f"Novel not found: {novel_id}")

    novel.status = NovelStatus.ADAPTING.value
    await db.commit()

    # Get chapters
    ch_result = await db.execute(
        select(NovelChapter)
        .where(NovelChapter.novel_id == novel_id)
        .order_by(NovelChapter.chapter_number)
    )
    chapters = ch_result.scalars().all()

    if max_chapters:
        chapters = chapters[:max_chapters]

    for chapter in chapters:
        try:
            await adapt_chapter(db, novel_id, chapter.chapter_number, style=style)
        except Exception as e:
            logger.error("Failed to adapt chapter %d: %s", chapter.chapter_number, e)

    novel.status = NovelStatus.ADAPTED.value
    await db.commit()
    await db.refresh(novel)
    return novel


async def link_to_project(
    db: AsyncSession,
    novel_id: str,
    project_id: str,
) -> Novel:
    """Link an adapted novel to a project."""
    result = await db.execute(select(Novel).where(Novel.id == novel_id))
    novel = result.scalar_one_or_none()
    if not novel:
        raise ValueError(f"Novel not found: {novel_id}")

    novel.project_id = project_id
    novel.status = NovelStatus.LINKED.value
    await db.commit()
    await db.refresh(novel)

    logger.info("Novel %s linked to project %s", novel_id, project_id)
    return novel


async def get_novel(db: AsyncSession, novel_id: str) -> Novel | None:
    """Get a novel by ID."""
    result = await db.execute(select(Novel).where(Novel.id == novel_id))
    return result.scalar_one_or_none()


async def list_novels(db: AsyncSession) -> list[Novel]:
    """List all novels."""
    result = await db.execute(select(Novel).order_by(Novel.created_at.desc()))
    return list(result.scalars().all())
