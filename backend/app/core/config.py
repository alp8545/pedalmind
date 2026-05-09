from pydantic import model_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DATABASE_URL: str = "postgresql+asyncpg://pedalmind:pedalmind@localhost:5432/pedalmind"
    GARMIN_CONSUMER_KEY: str = ""
    GARMIN_CONSUMER_SECRET: str = ""
    GARMIN_ENCRYPTION_KEY: str = ""  # Fernet key for encrypting OAuth tokens at rest
    GARMIN_EMAIL: str = ""  # Email for garth-based sync (single user)
    GARMIN_PASSWORD: str = ""  # Password for garth-based sync (single user)
    GARTH_TOKENS: str = ""  # base64-encoded garth token bundle for Railway
    APP_BASE_URL: str = "http://localhost:8000"
    OPENROUTER_API_KEY: str = ""
    OPENROUTER_BASE_URL: str = "https://openrouter.ai/api/v1"
    AI_MODEL_ANALYSIS: str = "nvidia/nemotron-3-super-120b-a12b:free"
    AI_MODEL_CHAT: str = "nvidia/nemotron-3-super-120b-a12b:free"
    S3_ENDPOINT: str = ""
    S3_BUCKET: str = "pedalmind-fits"
    S3_ACCESS_KEY: str = ""
    S3_SECRET_KEY: str = ""
    JWT_SECRET: str = "change-me-in-production"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_MINUTES: int = 1440
    FRONTEND_URL: str = "http://localhost:5173"
    ALLOWED_EMAILS: str = ""  # comma-separated allowlist; empty = open registration

    @model_validator(mode="after")
    def fix_database_url(self):
        """Railway injects DATABASE_URL as postgresql:// but asyncpg needs postgresql+asyncpg://"""
        url = self.DATABASE_URL
        if url.startswith("postgresql://"):
            self.DATABASE_URL = url.replace("postgresql://", "postgresql+asyncpg://", 1)
        elif url.startswith("postgres://"):
            self.DATABASE_URL = url.replace("postgres://", "postgresql+asyncpg://", 1)
        return self

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()
