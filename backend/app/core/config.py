from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "MedShare AI API"
    environment: str = "development"
    api_v1_prefix: str = "/api/v1"
    database_url: str = "postgresql+psycopg://localhost/medshare"
    jwt_secret: str = ""
    jwt_algorithm: str = "HS256"
    jwt_expiration_minutes: int = 60
    upload_dir: Path = Path("uploads")
    expiry_warning_days: int = 90
    medicine_extraction_provider: str = "gemini"
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.5-flash"
    cors_allowed_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()
