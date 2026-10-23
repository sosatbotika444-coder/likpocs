from functools import lru_cache
from pathlib import Path

from pydantic import EmailStr, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def normalize_database_url(url: str) -> str:
    """Use the installed psycopg 3 driver for PostgreSQL URLs from hosting platforms."""
    if url.startswith("postgres://"):
        return "postgresql+psycopg://" + url.removeprefix("postgres://")
    if url.startswith("postgresql://"):
        return "postgresql+psycopg://" + url.removeprefix("postgresql://")
    return url


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parents[2] / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "DormFlow API"
    environment: str = "development"
    database_url: str = "postgresql+psycopg://dormflow:dormflow@localhost:5432/dormflow"
    jwt_secret: str = "replace-this-secret-before-release"
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = Field(default=30, ge=5, le=1440)
    refresh_token_days: int = Field(default=14, ge=1, le=90)
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    initial_operator_email: EmailStr = "operator@example.com"
    initial_operator_password: str = ""
    initial_operator_name: str = "Bosh operator"
    timezone: str = "Asia/Tashkent"
    admins_can_adjust_billing: bool = False
    file_storage_backend: str = "local"
    file_local_directory: str = "./private-files"
    file_retention_days: int | None = Field(default=None, ge=1, le=36500)
    file_max_bytes: int = Field(default=10_485_760, ge=1024, le=104_857_600)
    public_app_url: str = "http://localhost:5173"
    s3_endpoint_url: str = ""
    s3_bucket: str = ""
    s3_region: str = "us-east-1"
    s3_access_key_id: str = ""
    s3_secret_access_key: str = ""

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
