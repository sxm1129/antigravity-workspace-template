from __future__ import annotations
"""Project ORM model — represents a comic drama project with status state machine."""

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import String, Text, DateTime, func
from sqlalchemy.dialects.mysql import LONGTEXT
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


# Valid status transitions (one-way flow)
PROJECT_STATUSES = [
    "IDEATION",
    "OUTLINE_REVIEW",
    "SCRIPT_REVIEW",
    "STORYBOARDING",
    "WAITING_ASSET_APPROVAL",
    "RENDERING",
    "COMPLETED",
]


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
        String(50), nullable=False, default="IDEATION"
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
        """Check if the project can transition to the target status."""
        if target_status not in PROJECT_STATUSES:
            return False
        current_idx = PROJECT_STATUSES.index(self.status)
        target_idx = PROJECT_STATUSES.index(target_status)
        return target_idx == current_idx + 1
