from __future__ import annotations
"""Novel ORM model — represents an imported novel with chapters for adaptation."""

import enum
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import String, Text, Integer, DateTime, func, ForeignKey
from sqlalchemy.dialects.mysql import LONGTEXT
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class NovelStatus(str, enum.Enum):
    """Novel import pipeline status."""
    UPLOADED = "UPLOADED"          # Raw text uploaded
    PARSING = "PARSING"            # Chapters being extracted
    PARSED = "PARSED"              # Chapters extracted
    ADAPTING = "ADAPTING"           # Being adapted to script
    ADAPTED = "ADAPTED"            # Script generated
    LINKED = "LINKED"              # Linked to a project


class Novel(Base):
    """An imported novel for adaptation to comic drama."""

    __tablename__ = "novels"
    __table_args__ = {
        "mysql_charset": "utf8mb4",
        "mysql_collate": "utf8mb4_unicode_ci",
    }

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: uuid.uuid4().hex[:36],
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    author: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    genre: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    raw_text: Mapped[Optional[str]] = mapped_column(LONGTEXT, nullable=True)
    total_chapters: Mapped[int] = mapped_column(Integer, default=0)
    total_words: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(
        String(50), nullable=False, default=NovelStatus.UPLOADED.value,
    )
    project_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("projects.id", ondelete="SET NULL"), nullable=True,
    )
    adaptation_config: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True,  # JSON: {chapters_per_episode, style, etc.}
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    chapters = relationship(
        "NovelChapter", back_populates="novel", cascade="all, delete-orphan",
        order_by="NovelChapter.chapter_number",
    )


class NovelChapter(Base):
    """A single chapter within an imported novel."""

    __tablename__ = "novel_chapters"
    __table_args__ = {
        "mysql_charset": "utf8mb4",
        "mysql_collate": "utf8mb4_unicode_ci",
    }

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: uuid.uuid4().hex[:36],
    )
    novel_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("novels.id", ondelete="CASCADE"), nullable=False,
    )
    chapter_number: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    content: Mapped[Optional[str]] = mapped_column(LONGTEXT, nullable=True)
    word_count: Mapped[int] = mapped_column(Integer, default=0)
    summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    adapted_script: Mapped[Optional[str]] = mapped_column(LONGTEXT, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    novel = relationship("Novel", back_populates="chapters")
