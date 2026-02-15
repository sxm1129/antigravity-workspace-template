from __future__ import annotations
"""Project ORM model — represents a comic drama project with bidirectional state machine."""

import enum
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import String, Text, DateTime, func
from sqlalchemy.dialects.mysql import LONGTEXT
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class ProjectStatus(str, enum.Enum):
    """Project lifecycle statuses — supports forward and rollback transitions."""

    DRAFT = "DRAFT"
    OUTLINE_REVIEW = "OUTLINE_REVIEW"
    SCRIPT_REVIEW = "SCRIPT_REVIEW"
    STORYBOARD = "STORYBOARD"
    PRODUCTION = "PRODUCTION"
    COMPOSING = "COMPOSING"
    COMPLETED = "COMPLETED"


# Ordered list for index-based navigation
_STATUS_ORDER: list[ProjectStatus] = list(ProjectStatus)

# Explicit valid transitions: status -> set of reachable statuses
VALID_TRANSITIONS: dict[ProjectStatus, set[ProjectStatus]] = {
    ProjectStatus.DRAFT: {ProjectStatus.OUTLINE_REVIEW},
    ProjectStatus.OUTLINE_REVIEW: {ProjectStatus.SCRIPT_REVIEW, ProjectStatus.DRAFT},
    ProjectStatus.SCRIPT_REVIEW: {ProjectStatus.STORYBOARD, ProjectStatus.OUTLINE_REVIEW},
    ProjectStatus.STORYBOARD: {ProjectStatus.PRODUCTION, ProjectStatus.SCRIPT_REVIEW},
    ProjectStatus.PRODUCTION: {ProjectStatus.COMPOSING, ProjectStatus.STORYBOARD},
    ProjectStatus.COMPOSING: {ProjectStatus.COMPLETED, ProjectStatus.PRODUCTION},
    ProjectStatus.COMPLETED: set(),  # terminal state
}


class Project(Base):
    """A comic drama project with its script and world outline."""

    __tablename__ = "projects"
    __table_args__ = {
        "mysql_charset": "utf8mb4",
        "mysql_collate": "utf8mb4_unicode_ci",
    }

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: uuid.uuid4().hex[:36],
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    logline: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    world_outline: Mapped[Optional[str]] = mapped_column(
        LONGTEXT, nullable=True,
    )
    full_script: Mapped[Optional[str]] = mapped_column(
        LONGTEXT, nullable=True,
    )
    status: Mapped[str] = mapped_column(
        String(50), nullable=False, default=ProjectStatus.DRAFT.value
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    characters = relationship(
        "Character", back_populates="project", cascade="all, delete-orphan"
    )
    scenes = relationship(
        "Scene",
        back_populates="project",
        cascade="all, delete-orphan",
        order_by="Scene.sequence_order",
    )

    def can_transition_to(self, target_status: str) -> bool:
        """Check if the project can transition to the target status (forward or rollback)."""
        try:
            current = ProjectStatus(self.status)
            target = ProjectStatus(target_status)
        except ValueError:
            return False
        return target in VALID_TRANSITIONS.get(current, set())

    def is_rollback(self, target_status: str) -> bool:
        """Check if the target status is a rollback (moving backward)."""
        try:
            current_idx = _STATUS_ORDER.index(ProjectStatus(self.status))
            target_idx = _STATUS_ORDER.index(ProjectStatus(target_status))
        except (ValueError, IndexError):
            return False
        return target_idx < current_idx
