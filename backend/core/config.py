from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    # Security Configuration
    API_KEY: str | None = None
    RATE_LIMIT_DEFAULT: str = "10/minute"
    
    # Allows loading from .env file
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

settings = Settings()
