from pydantic import BaseSettings, Field


class Settings(BaseSettings):
    env: str = "dev"

    # Tokens (optional but recommended for GitHub rate limits)
    github_token: str | None = Field(default=None, env="GITHUB_TOKEN")

    # HTTP behavior
    request_timeout_s: float = 15.0
    http_retries: int = 3

    class Config:
        case_sensitive = False


settings = Settings()
