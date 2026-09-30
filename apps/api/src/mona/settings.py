from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")

    database_url: str
    mona_env: Literal["dev", "prod"] = "dev"
    mona_data_dir: Path = Path("/data")
    mona_service_key: SecretStr | None = None
    openrouter_api_key: SecretStr | None = None
    mona_owner_password: SecretStr | None = None
    mona_iban_pepper: SecretStr | None = None
    mona_seed_overlay: Path | None = None
    hermes_api_key: SecretStr | None = None
    hermes_url: str = "http://hermes:8642"

    @property
    def libpq_url(self) -> str:
        """DATABASE_URL without the SQLAlchemy driver suffix, for psycopg and Procrastinate."""
        scheme, sep, rest = self.database_url.partition("://")
        return scheme.split("+", 1)[0] + sep + rest


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
