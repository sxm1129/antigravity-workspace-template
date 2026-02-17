from __future__ import annotations
"""Episode ORM model — represents a single episode within a comic drama project."""

import enum
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import ForeignKey, Integer, String, Text, DateTime, func
from sqlalchemy.dialects.mysql import LONGTEXT
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class EpisodeStatus(str, enum.Enum):
    """Episode lifecycle statuses."""

    SCRIPT_GENERATING = "SCRIPT_GENERATING"
    SCRIPT_REVIEW = "SCRIPT_REVIEW"
    STORYBOARD = "STORYBOARD"
    PRODUCTION = "PRODUCTION"
    COMPOSING = "COMPOSING"
    COMPLETED = "COMPLETED"


# Explicit valid transitions for episode status
EPISODE_VALID_TRANSITIONS: dict[EpisodeStatus, set[EpisodeStatus]] = {
    EpisodeStatus.SCRIPT_GENERATING: {EpisodeStatus.SCRIPT_REVIEW},
    EpisodeStatus.SCRIPT_REVIEW: {EpisodeStatus.STORYBOARD, EpisodeStatus.SCRIPT_GENERATING},
    EpisodeStatus.STORYBOARD: {EpisodeStatus.PRODUCTION, EpisodeStatus.SCRIPT_REVIEW},
    EpisodeStatus.PRODUCTION: {EpisodeStatus.COMPOSING, EpisodeStatus.STORYBOARD},
    EpisodeStatus.COMPOSING: {EpisodeStatus.COMPLETED, EpisodeStatus.PRODUCTION},
    EpisodeStatus.COMPLETED: {EpisodeStatus.SCRIPT_REVIEW, EpisodeStatus.COMPOSING},
}


class Episode(Base):
    """A single episode within a project, with its own script and scene pipeline."""

    __tablename__ = "episodes"
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
    episode_number: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    title: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    synopsis: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    full_script: Mapped[Optional[str]] = mapped_column(LONGTEXT, nullable=True)
    final_video_path: Mapped[Optional[str]] = mapped_column(
        String(1024), nullable=True
    )
    status: Mapped[str] = mapped_column(
        String(50), nullable=False, default=EpisodeStatus.SCRIPT_GENERATING.value
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    project = relationship("Project", back_populates="episodes")
    scenes = relationship(
        "Scene",
        back_populates="episode",
        cascade="all, delete-orphan",
        order_by="Scene.sequence_order",
    )

    def can_transition_to(self, target_status: str) -> bool:
        """Check if the episode can transition to the target status."""
        try:
            current = EpisodeStatus(self.status)
            target = EpisodeStatus(target_status)
        except ValueError:
            return False
        return target in EPISODE_VALID_TRANSITIONS.get(current, set())
