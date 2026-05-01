"""App configuration from environment variables."""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    aws_region: str = "us-east-1"
    s3_bucket: str = "interviewer-poc-audio-484626021127"
    claude_model_id: str = "us.anthropic.claude-sonnet-4-5-20250929-v1:0"
    nova_sonic_model_id: str = "amazon.nova-2-sonic-v1:0"
    database_url: str = "sqlite+aiosqlite:///./interviewer.db"
    presigned_url_ttl_sec: int = 3600
    # Dev-only: comma-separated origins for CORS
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"

    # Cognito (empty = auth disabled, for local dev)
    cognito_region: str = "us-east-1"
    cognito_user_pool_id: str = ""
    cognito_client_id: str = ""


settings = Settings()
