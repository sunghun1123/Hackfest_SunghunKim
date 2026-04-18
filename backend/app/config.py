from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str = Field(..., alias="DATABASE_URL")
    google_places_api_key: str = Field(..., alias="GOOGLE_PLACES_API_KEY")
    gemini_api_key: str = Field(..., alias="GEMINI_API_KEY")
    env: str = Field(default="local", alias="ENV")

    cors_origins: list[str] = Field(
        default_factory=lambda: ["*"], alias="CORS_ORIGINS"
    )

    # Auto-detected at startup; overridable via env for tests.
    postgis_enabled: bool = Field(default=False, alias="POSTGIS_ENABLED")

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_origins(cls, v):
        if isinstance(v, str):
            return [o.strip() for o in v.split(",") if o.strip()]
        return v


settings = Settings()
