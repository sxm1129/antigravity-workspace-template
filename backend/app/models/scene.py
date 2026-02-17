from __future__ import annotations
"""Scene ORM model — the atomic unit of a comic drama (one storyboard panel)."""

import enum
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class SceneStatus(str, enum.Enum):
    """Scene lifecycle statuses."""

    PENDING = "PENDING"
    GENERATING = "GENERATING"
    REVIEW = "REVIEW"
    APPROVED = "APPROVED"
    VIDEO_GEN = "VIDEO_GEN"
    READY = "READY"


class Scene(Base):
    """A single storyboard panel with its prompts and generated asset paths."""

    __tablename__ = "scenes"
    __table_args__ = {
        "mysql_charset": "utf8mb4",
        "mysql_collate": "utf8mb4_unicode_ci",
    }

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: uuid.uuid4().hex[:36],
    )
    project_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    episode_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("episodes.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    sequence_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Content fields
    dialogue_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    prompt_visual: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    prompt_motion: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    sfx_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Local asset paths (relative to media_volume)
    local_audio_path: Mapped[Optional[str]] = mapped_column(
        String(1024), nullable=True
    )
    local_image_path: Mapped[Optional[str]] = mapped_column(
        String(1024), nullable=True
    )
    local_video_path: Mapped[Optional[str]] = mapped_column(
        String(1024), nullable=True
    )
    audio_duration: Mapped[Optional[float]] = mapped_column(
        Float, nullable=True
    )
    video_duration: Mapped[Optional[float]] = mapped_column(
        Float, nullable=True
    )

    # Scene status
    status: Mapped[str] = mapped_column(
        String(50), nullable=False, default=SceneStatus.PENDING.value
    )

    # Timestamps
    created_at: Mapped[Optional[datetime]] = mapped_column(
        nullable=True, server_default=func.now()
    )
    updated_at: Mapped[Optional[datetime]] = mapped_column(
        nullable=True, server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    project = relationship("Project", back_populates="scenes")
    episode = relationship("Episode", back_populates="scenes")
    asset_versions = relationship(
        "AssetVersion", back_populates="scene", cascade="all, delete-orphan"
    )
