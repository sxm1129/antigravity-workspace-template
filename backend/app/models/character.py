from __future__ import annotations
"""Character ORM model — identity asset for visual consistency across scenes."""

import uuid
from datetime import datetime
from typing import Optional, List

from sqlalchemy import JSON, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Character(Base):
    """A character with visual identity references for consistent image generation."""

    __tablename__ = "characters"
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
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    appearance_prompt: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    nano_identity_refs: Mapped[Optional[list]] = mapped_column(
        JSON, nullable=True, default=list
    )
    reference_image_path: Mapped[Optional[str]] = mapped_column(
        String(1024), nullable=True
    )
    style_tags: Mapped[Optional[list]] = mapped_column(
        JSON, nullable=True, default=list
    )

    # Timestamps
    created_at: Mapped[Optional[datetime]] = mapped_column(
        nullable=True, server_default=func.now()
    )
    updated_at: Mapped[Optional[datetime]] = mapped_column(
        nullable=True, server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    project = relationship("Project", back_populates="characters")

