from functools import lru_cache
from pathlib import Path

from pydantic import SecretStr, field_validator
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

    s3_bucket_name: str
    aws_region: str = "us-east-1"
    aws_user_name: str
    aws_access_key_id: SecretStr
    aws_secret_access_key: SecretStr

    # Root for both the download-staging area and the post-store local cache, keyed
    # by audio_files.storage_key (database-schema.md §4.2). Relative paths resolve
    # against REPO_ROOT, matching POSTGRES_DATA_DIR's convention.
    local_cache_dir: Path = Path("data/audio-cache")

    youtube_api_key: SecretStr

    @field_validator("local_cache_dir")
    @classmethod
    def _resolve_local_cache_dir(cls, value: Path) -> Path:
        return value if value.is_absolute() else REPO_ROOT / value

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

    def database_url(self) -> str:
        password = self.postgres_password.get_secret_value()
        return (
            f"postgresql+psycopg://{self.postgres_user}:{password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )


@lru_cache
def get_settings() -> Settings:
    # Required fields are populated from env/.env/config.toml at runtime, not
    # passed here; the type checker can't see that, hence the ignore.
    return Settings()  # type: ignore[call-arg]
