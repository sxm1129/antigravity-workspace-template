"""Phase 4 schema updates — asset_versions table, project/character new columns

Revision ID: 0001
Revises: None
Create Date: 2026-02-15 16:08:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- asset_versions (new table) ---
    op.create_table(
        "asset_versions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("scene_id", sa.String(36), sa.ForeignKey("scenes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("asset_type", sa.String(20), nullable=False, comment="IMAGE | AUDIO | VIDEO"),
        sa.Column("version", sa.Integer, nullable=False, server_default="1"),
        sa.Column("provider", sa.String(100), nullable=True),
        sa.Column("file_path", sa.String(500), nullable=False),
        sa.Column("quality_score", sa.Float, nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column("metadata_json", sa.Text, nullable=True),
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_unicode_ci",
    )
    op.create_index("ix_asset_versions_scene_id", "asset_versions", ["scene_id"])
    op.create_index("ix_asset_versions_active", "asset_versions", ["scene_id", "asset_type", "is_active"])

    # --- projects: new columns ---
    op.add_column("projects", sa.Column("mode", sa.String(20), nullable=True, server_default="STANDARD"))
    op.add_column("projects", sa.Column("style_preset", sa.String(50), nullable=True, server_default="default"))
    op.add_column("projects", sa.Column("draft_progress", sa.Text, nullable=True))
    op.add_column("projects", sa.Column("final_video_path", sa.String(500), nullable=True))

    # --- characters: new columns ---
    op.add_column("characters", sa.Column("reference_image_path", sa.String(500), nullable=True))
    op.add_column("characters", sa.Column("style_tags", sa.Text, nullable=True))


def downgrade() -> None:
    # --- characters: drop new columns ---
    op.drop_column("characters", "style_tags")
    op.drop_column("characters", "reference_image_path")

    # --- projects: drop new columns ---
    op.drop_column("projects", "final_video_path")
    op.drop_column("projects", "draft_progress")
    op.drop_column("projects", "style_preset")
    op.drop_column("projects", "mode")

    # --- asset_versions: drop table ---
    op.drop_index("ix_asset_versions_active", table_name="asset_versions")
    op.drop_index("ix_asset_versions_scene_id", table_name="asset_versions")
    op.drop_table("asset_versions")
