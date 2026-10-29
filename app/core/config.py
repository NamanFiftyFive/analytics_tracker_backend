import json
from functools import lru_cache
from pathlib import Path
from typing import Annotated
from urllib.parse import quote

from pydantic import field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

# backend/.env, found from this file's location so it works from any working directory.
ENV_FILE = Path(__file__).resolve().parents[2] / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ENV_FILE, extra="ignore")

    APP_NAME: str = "Analytics API"
    ENVIRONMENT: str = "local"
    DEBUG: bool = False
    API_V1_PREFIX: str = "/api/v1"

    POSTGRES_USER: str
    POSTGRES_PASSWORD: str
    POSTGRES_DB: str
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432
    DB_POOL_MIN_SIZE: int = 2
    DB_POOL_MAX_SIZE: int = 20

    JWT_SECRET_KEY: str
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # NoDecode: read the raw text and parse it below, so both JSON and a plain comma list work.
    CORS_ORIGINS: Annotated[list[str], NoDecode] = []

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def parse_cors_origins(cls, value: object) -> object:
        """Accept `["https://a.com","https://b.com"]`, `https://a.com,https://b.com` or empty."""
        if not isinstance(value, str):
            return value
        text = value.strip()
        if text.startswith("["):
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                # Shells strip the inner quotes: [https://a.com,https://b.com]
                text = text.strip("[]")
        return [origin.strip().strip("\"'") for origin in text.split(",") if origin.strip()]

    @property
    def database_url(self) -> str:
        # Encode user and password: characters like @ : / # would otherwise break the URL.
        user = quote(self.POSTGRES_USER, safe="")
        password = quote(self.POSTGRES_PASSWORD, safe="")
        return (
            f"postgresql://{user}:{password}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )


@lru_cache
def get_settings() -> Settings:
    # Required fields come from environment variables / .env at runtime,
    # which the type checker cannot see.
    return Settings()  # type: ignore[call-arg]


settings = get_settings()
