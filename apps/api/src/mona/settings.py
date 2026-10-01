from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import SecretStr, field_validator
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
    mona_llm_model: str = "qwen/qwen3.7-flash"
    mona_llm_backend: Literal["openrouter", "llama-server"] = "openrouter"
    mona_llm_base_url: str | None = None
    mona_hermes_home: Path | None = None
    mona_hermes_seed: Path | None = None
    mona_hermes_env_keys: str = ""
    mona_uid: int | None = None
    mona_gid: int | None = None
    hermes_uid: int | None = None
    hermes_gid: int | None = None

    @field_validator("mona_hermes_home", "mona_hermes_seed", "mona_seed_overlay", mode="before")
    @classmethod
    def _empty_is_unset(cls, v: object) -> object:
        return None if v == "" else v

    @property
    def libpq_url(self) -> str:
        """DATABASE_URL without the SQLAlchemy driver suffix, for psycopg and Procrastinate."""
        scheme, sep, rest = self.database_url.partition("://")
        return scheme.split("+", 1)[0] + sep + rest


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
