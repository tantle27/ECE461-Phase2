from pydantic import BaseSettings, Field  # type: ignore


class Settings(BaseSettings):  # type: ignore
    env: str = "dev"

    # Tokens (optional but recommended for GitHub rate limits)
    GH_TOKEN: str | None = Field(default=None, env="GH_TOKEN")  # type: ignore

    # HTTP behavior
    request_timeout_s: float = 15.0
    http_retries: int = 3

    class Config:
        case_sensitive = False


settings = Settings()
