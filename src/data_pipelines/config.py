from functools import lru_cache
from pathlib import Path

from pydantic import SecretStr
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
    TomlConfigSettingsSource,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """Secrets come from .env (gitignored); non-secret values come from config.toml
    (committed). See .env.example and config.toml for what belongs where."""

    model_config = SettingsConfigDict(
        env_file=REPO_ROOT / ".env",
        toml_file=REPO_ROOT / "config.toml",
        extra="ignore",
    )

    postgres_user: str = "kol_torah"
    postgres_password: SecretStr
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "kol_torah"
    lab_db: str = "kol_torah_lab"

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        return (
            init_settings,
            env_settings,
            dotenv_settings,
            TomlConfigSettingsSource(settings_cls),
            file_secret_settings,
        )

    def database_url(self, *, lab: bool = False) -> str:
        db_name = self.lab_db if lab else self.postgres_db
        password = self.postgres_password.get_secret_value()
        return (
            f"postgresql+psycopg://{self.postgres_user}:{password}"
            f"@{self.postgres_host}:{self.postgres_port}/{db_name}"
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
