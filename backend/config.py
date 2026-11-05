from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_ROOT = Path(__file__).resolve().parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=BACKEND_ROOT / ".env", extra="ignore")

    gemini_api_key: SecretStr = SecretStr("")
    gemini_model: str = ""
    ai_poster_timeout_seconds: float = Field(default=30, gt=0, le=60)
    database_url: str = "sqlite:///./data/amp.db"
    upload_dir: Path = BACKEND_ROOT / "uploads" / "pending"
    upload_ttl_hours: int = Field(default=24, ge=1)
    local_demo: bool = False
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    @property
    def database_path(self) -> Path:
        prefix = "sqlite:///"
        if not self.database_url.startswith(prefix):
            raise ValueError("Poster venue lookup requires a SQLite DATABASE_URL")
        path = Path(self.database_url[len(prefix) :])
        return path if path.is_absolute() else BACKEND_ROOT / path

    @property
    def allowed_origins(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]
