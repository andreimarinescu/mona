from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import SecretStr, ValidationError, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class SettingsError(RuntimeError):
    """A refused configuration; the message names variables, never their values."""


class Settings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")

    database_url: str
    mona_env: Literal["dev", "prod"]
    mona_data_dir: Path = Path("/data")
    mona_service_key: SecretStr | None = None
    openrouter_api_key: SecretStr | None = None
    mona_owner_password: SecretStr | None = None
    mona_iban_pepper: SecretStr | None = None
    mona_seed_overlay: Path | None = None
    hermes_api_key: SecretStr | None = None
    hermes_url: str = "http://hermes:8642"
    mona_attach_root: Path = Path("/opt/data/cache")
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

    telegram_bot_token: SecretStr | None = None
    mona_public_origin: str | None = None
    mona_trusted_proxy: str | None = None
    mona_build: str | None = None

    @field_validator("mona_hermes_home", "mona_hermes_seed", "mona_seed_overlay", mode="before")
    @classmethod
    def _empty_is_unset(cls, v: object) -> object:
        return None if v == "" else v

    @property
    def libpq_url(self) -> str:
        """DATABASE_URL without the SQLAlchemy driver suffix, for psycopg and Procrastinate."""
        scheme, sep, rest = self.database_url.partition("://")
        return scheme.split("+", 1)[0] + sep + rest

    @property
    def proxies(self) -> frozenset[str]:
        """Addresses whose `X-Forwarded-*` headers are trusted (C9 §4.3: Caddy only)."""
        raw = self.mona_trusted_proxy or ""
        return frozenset(p.strip() for p in raw.split(",") if p.strip())


def load_settings() -> Settings:
    """Settings from the environment; a missing or bad variable is named without its value, and
    `MONA_ENV=prod` runs the C9 §2.1 assertions A1–A2."""
    try:
        settings = Settings()  # type: ignore[call-arg]
    except ValidationError as e:
        names = sorted({str(err["loc"][0]).upper() for err in e.errors() if err.get("loc")})
        raise SettingsError(f"invalid or missing settings: {', '.join(names)}") from None
    if settings.mona_env == "prod":
        from mona.privacy import assert_process_env

        assert_process_env(settings)
    return settings


@lru_cache
def get_settings() -> Settings:
    return load_settings()
