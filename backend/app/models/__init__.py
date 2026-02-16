"""ORM model package — registers all models with Base.metadata."""

from app.models.project import Project, ProjectStatus, ProjectMode, VALID_TRANSITIONS
from app.models.episode import Episode, EpisodeStatus, EPISODE_VALID_TRANSITIONS
from app.models.character import Character
from app.models.scene import Scene, SceneStatus
from app.models.asset_version import AssetVersion, AssetType

__all__ = [
    "Project",
    "ProjectStatus",
    "ProjectMode",
    "VALID_TRANSITIONS",
    "Episode",
    "EpisodeStatus",
    "EPISODE_VALID_TRANSITIONS",
    "Character",
    "Scene",
    "SceneStatus",
    "AssetVersion",
    "AssetType",
]
