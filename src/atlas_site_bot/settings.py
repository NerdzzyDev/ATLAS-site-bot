from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    site_url: str = "https://example.com"
    database_url: str = "postgresql+asyncpg://postgres:postgres@db:5432/atlas_bot"
    telegram_enabled: bool = True
    telegram_bot_token: str = ""
    telegram_chat_ids: list[int] = []
    telegram_retry_attempts: int = 3
    telegram_retry_delay_seconds: float = 1.0

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    @field_validator("telegram_chat_ids", mode="before")
    @classmethod
    def _parse_chat_ids(cls, value):  # noqa: ANN001
        if value is None or value == "":
            return []
        if isinstance(value, str):
            return [int(item.strip()) for item in value.split(",") if item.strip()]
        return value
