"""Application configuration loaded from environment variables."""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Typed settings sourced from environment (see .env.example)."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)

    # Runtime
    environment: str = "development"
    log_level: str = "INFO"

    # Database
    database_url: str = "postgresql+asyncpg://exam:change_me_postgres@postgres:5432/exam_db"

    # Redis
    redis_url: str = "redis://redis:6379/0"

    # Security
    jwt_secret: str = "change_me_to_a_long_random_secret"
    jwt_algorithm: str = "HS256"
    jwt_expire_hours: int = 8
    bcrypt_rounds: int = 12

    # Encryption
    pbkdf2_iterations: int = 600_000

    # Uploads
    upload_dir: str = "/app/uploads"
    max_upload_mb: int = 20

    # Safe Exam Browser — MẶC ĐỊNH TẮT (hệ thống dùng kiosk riêng, không dùng SEB).
    # Chỉ bật (SEB_ENFORCE=true trong .env) nếu thật sự dùng Safe Exam Browser.
    seb_start_url: str = "http://exam-server.local/thisinh/"
    seb_enforce: bool = False
    # Config Key from the SEB Config Tool (preferred — version-proof). When set,
    # it overrides the value computed from our settings template (see AD-57).
    seb_config_key: str = ""


    # Rate limiting — throttle password brute-force on the admin login.
    admin_login_rate: str = "10/2minutes"
    exam_login_rate: str = "10/2minutes"

    # CORS
    cors_origins: str = "http://localhost,http://exam-server.local"

    @property
    def is_production(self) -> bool:
        return self.environment.lower() == "production"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    """Cached settings singleton."""
    return Settings()


settings = get_settings()
