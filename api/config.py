"""Environment-backed configuration for the Trace API."""

from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables or .env."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        env_ignore_empty=True,
        extra="ignore",
    )

    data_dir: Path = Path("data")
    database_url: str | None = None
    max_upload_size: int = 2 * 1024 * 1024 * 1024
    max_request_size: int = 2 * 1024 * 1024
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:5173"])
    engine_mode: Literal["real", "fake"] = "fake"
    auth_mode: Literal["none", "apikey", "jwt"] = "none"
    api_key: str | None = None
    jwt_secret: str | None = None
    demo_username: str | None = None
    demo_password: str | None = None
    demo_mode: bool = True
    serve_frontend: bool = False
    max_concurrent_jobs: int = 1
    job_timeout: int = 3600
    fake_step_seconds: float = 1.5
    report_engine: Literal["auto", "weasyprint", "reportlab"] = "auto"
    app_version: str = "0.1.0"

    @property
    def resolved_database_url(self) -> str:
        """Return configured URL or a SQLite database below the data directory."""
        if self.database_url:
            return self.database_url
        return f"sqlite:///{(self.data_dir / 'trace.db').as_posix()}"
