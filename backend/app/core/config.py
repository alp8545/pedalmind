from pydantic import model_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DATABASE_URL: str = "postgresql+asyncpg://pedalmind:pedalmind@localhost:5432/pedalmind"
    GARMIN_EMAIL: str = ""
    GARMIN_PASSWORD: str = ""
    GARMIN_CLIENT_ID: str = ""
    GARMIN_CLIENT_SECRET: str = ""
    GARMIN_REDIRECT_URI: str = "http://localhost:8000/api/auth/garmin/callback"
    ANTHROPIC_API_KEY: str = ""
    AI_MODEL_ANALYSIS: str = "claude-haiku-4-5-20251001"
    AI_MODEL_CHAT: str = "claude-sonnet-4-6"
    S3_ENDPOINT: str = ""
    S3_BUCKET: str = "pedalmind-fits"
    S3_ACCESS_KEY: str = ""
    S3_SECRET_KEY: str = ""
    JWT_SECRET: str = "change-me-in-production"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_MINUTES: int = 1440
    FRONTEND_URL: str = "http://localhost:5173"

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


settings = Settings()
