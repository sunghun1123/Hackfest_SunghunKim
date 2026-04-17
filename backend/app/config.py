from pydantic import Field
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


settings = Settings()
