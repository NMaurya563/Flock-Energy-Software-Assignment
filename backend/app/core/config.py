from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=Path(__file__).resolve().parents[2] / ".env", extra="ignore")
    portal_url: str = "https://urja-ops.flockenergy.tech"
    portal_username: str = ""
    portal_password: SecretStr = SecretStr("")
    request_timeout: float = Field(default=15, gt=0, le=120)
    export_ttl_seconds: int = Field(default=60, ge=0, le=3600)
    upstream_attempts: int = Field(default=3, ge=1, le=5)
