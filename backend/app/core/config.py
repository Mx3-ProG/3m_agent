from functools import lru_cache
from pathlib import Path

import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_prefix="THREEM_", extra="ignore", case_sensitive=False
    )

    app_name: str = "3M API"
    env: str = "development"
    database_url: str = "sqlite+aiosqlite:///./data/3m.sqlite3"
    api_token: str = "change-me-local-only"
    allowed_origins: str = "http://localhost:3000,https://localhost:3000"
    default_llm_provider: str = "demo"
    default_llm_model: str = "3m-demo"
    max_tts_characters: int = 2500
    max_execution_steps: int = 8
    tool_timeout_seconds: float = 15.0
    confirmation_ttl_minutes: int = 15
    calendar_provider: str = "demo"
    apple_calendar_bridge_path: str = "native/apple-calendar-bridge/.build/apple-calendar-bridge"
    apple_calendar_identifier: str = ""
    context_recent_messages: int = 20
    context_budget_characters: int = 16_000
    conversation_summary_threshold: int = 24
    user_timezone: str = "Europe/Paris"

    @property
    def origins(self) -> list[str]:
        return [origin.strip() for origin in self.allowed_origins.split(",") if origin.strip()]


class Personality(BaseModel):
    name: str = "3M"
    language: str = "fr"
    traits: list[str] = Field(default_factory=list)
    response_style: str = ""
    system_instructions: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()


@lru_cache
def get_personality() -> Personality:
    path = Path("config/personality.yaml")
    if not path.exists():
        return Personality()
    return Personality.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
