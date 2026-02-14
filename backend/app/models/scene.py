from __future__ import annotations
"""Scene ORM model — the atomic unit of a comic drama (one storyboard panel)."""

import uuid
from typing import Optional

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


# Scene status lifecycle
SCENE_STATUSES = [
    "PENDING",
    "ASSET_GENERATING",
    "WAITING_HUMAN_APPROVAL",
    "APPROVED_BY_HUMAN",
    "VIDEO_GENERATING",
    "READY",
]


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

    # Scene status
    status: Mapped[str] = mapped_column(
        String(50), nullable=False, default="PENDING"
    )

    # Relationships
    project = relationship("Project", back_populates="scenes")
