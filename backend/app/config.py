from functools import lru_cache
from ipaddress import ip_address
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from pydantic import EmailStr, Field, field_validator
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

    app_name: str = "RS Best Hostel API"
    environment: str = "development"
    database_url: str = "postgresql+psycopg://dormflow:dormflow@localhost:5432/dormflow"
    jwt_secret: str = "replace-this-secret-before-release"
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = Field(default=30, ge=5, le=1440)
    refresh_token_days: int = Field(default=14, ge=1, le=90)
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173,https://dormflows.netlify.app"
    initial_operator_email: EmailStr = "operator@example.com"
    initial_operator_password: str = ""
    initial_operator_name: str = "Bosh operator"
    timezone: str = "Asia/Tashkent"
    admins_can_adjust_billing: bool = False
    file_storage_backend: str = "local"
    file_local_directory: str = "./private-files"
    # Safe operational default; deployments can replace this with the approved policy.
    file_retention_days: int | None = Field(default=365, ge=1, le=36500)
    file_max_bytes: int = Field(default=10_485_760, ge=1024, le=104_857_600)
    file_max_image_pixels: int = Field(default=24_000_000, ge=1_000_000, le=100_000_000)
    public_app_url: str = "https://dormflows.netlify.app"
    openrouter_api_key: str = ""
    openrouter_model: str = "openrouter/free"
    openrouter_enabled: bool = True
    openrouter_require_zdr: bool = True
    s3_endpoint_url: str = ""
    s3_bucket: str = ""
    s3_region: str = "us-east-1"
    s3_access_key_id: str = ""
    s3_secret_access_key: str = ""

    @field_validator("public_app_url")
    @classmethod
    def validate_public_app_url(cls, value: str) -> str:
        parsed = urlsplit(value.strip())
        if parsed.scheme not in {"http", "https"} or not parsed.netloc or parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError("PUBLIC_APP_URL faqat HTTP(S) sayt manzili bo'lishi mumkin.")
        return urlunsplit((parsed.scheme, parsed.netloc, parsed.path.rstrip("/"), "", ""))

    @property
    def public_app_base_url(self) -> str:
        parsed = urlsplit(self.public_app_url)
        hostname = (parsed.hostname or "").lower()
        is_local_host = hostname in {"localhost", "localhost.localdomain"}
        try:
            is_local_host = is_local_host or ip_address(hostname).is_loopback
        except ValueError:
            pass
        # Invitation URLs must point to the public student form, even when an
        # old local-development override is still present in the environment.
        if is_local_host:
            return "https://dormflows.netlify.app"
        return self.public_app_url

    @property
    def public_app_origin(self) -> str:
        parsed = urlsplit(self.public_app_base_url)
        return f"{parsed.scheme}://{parsed.netloc}"

    @property
    def cors_origin_list(self) -> list[str]:
        configured = [origin.strip().rstrip("/") for origin in self.cors_origins.split(",") if origin.strip()]
        if self.public_app_origin not in configured:
            configured.append(self.public_app_origin)
        return configured


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
