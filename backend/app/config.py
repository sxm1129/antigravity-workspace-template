from __future__ import annotations
"""Application configuration using Pydantic Settings."""

from functools import lru_cache
from urllib.parse import quote_plus

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """MotionWeaver application settings.

    Loaded from environment variables or .env file.
    """

    # --- Application ---
    APP_NAME: str = "MotionWeaver"
    DEBUG: bool = True
    USE_MOCK_API: bool = True

    # --- Database (MySQL 8.0+) ---
    DB_HOST: str = "39.98.37.143"
    DB_PORT: int = 3306
    DB_USER: str = "root"
    DB_PASSWORD: str = ""
    DB_NAME: str = "comicdrama"

    @property
    def DATABASE_URL(self) -> str:
        """Async MySQL connection string using asyncmy driver."""
        encoded_password = quote_plus(self.DB_PASSWORD)
        return (
            f"mysql+asyncmy://{self.DB_USER}:{encoded_password}"
            f"@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"
            "?charset=utf8mb4"
        )

    # --- Redis ---
    REDIS_URL: str = "redis://localhost:6379/0"

    # --- Media Volume ---
    MEDIA_VOLUME: str = "media_volume"

    # --- OpenRouter (Story AI + Image Gen) ---
    OPENROUTER_BASE_URL: str = "https://openrouter.ai/api/v1"
    OPENROUTER_API_KEY: str = ""
    STORY_MODEL: str = "google/gemini-3-flash-preview"
    IMAGE_MODEL: str = "google/gemini-2.5-flash-image"

    # --- Flux (Private Deployment) ---
    FLUX_API_BASE: str = "http://47.92.252.119:8080/api/v1"
    FLUX_API_KEY: str = "fx-commonwtpKmZL6XPKFrqrnvDRszLxtjM0w62DHULzGfwqL2K"
    FLUX_MODEL: str = "FLUX.1-schnell"
    FLUX_TIMEOUT: int = 120

    # --- Volcengine Ark (Video Generation) ---
    ARK_API_KEY: str = ""
    ARK_VIDEO_MODEL: str = "doubao-seedance-1-0-lite-i2v-250428"
    ARK_ENDPOINT: str = "https://ark.cn-beijing.volces.com/api/v3"

    # --- Legacy keys (kept for backward compat) ---
    GEMINI_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-2.5-pro"

    # --- IndexTTS ---
    INDEX_TTS_URL: str = "http://39.102.122.9:8049"
    INDEX_TTS_VOICE: str = "zh_male_tech"

    # --- Quality Scoring ---
    ENABLE_AUTO_SCORING: bool = False
    QUALITY_THRESHOLD: float = 0.6
    MAX_QUALITY_RETRIES: int = 2

    # --- Image Provider Strategy ---
    IMAGE_PROVIDERS: str = "flux,openrouter"  # comma-separated, in priority order

    # --- Video Provider Strategy ---
    VIDEO_PROVIDERS: str = "seedance,ffmpeg"  # comma-separated, in priority order

    # --- Convenience alias ---
    @property
    def OPENROUTER_MODEL(self) -> str:
        return self.STORY_MODEL

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }


@lru_cache
def get_settings() -> Settings:
    """Get cached application settings singleton."""
    return Settings()
