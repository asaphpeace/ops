from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Database
    database_url: str = "postgresql+asyncpg://sedna:changeme@db:5432/sedna_ops"

    # Auth
    secret_key: str = "dev-secret-key-change-in-production"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 480  # 8 hours

    # CORS
    cors_origins: list[str] = ["http://localhost", "http://localhost:5173", "http://localhost:80"]

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, v: object) -> object:
        if isinstance(v, str):
            return [o.strip() for o in v.split(",") if o.strip()]
        return v

    # Jira — optional; polling disabled if token is empty
    jira_base_url: str = ""
    jira_email: str = ""
    jira_api_token: str = ""

    # Slack — optional; notifications logged locally if empty
    slack_webhook_url: str = ""

    # Anthropic — optional; AI use cases disabled if empty
    anthropic_api_key: str = ""

    @property
    def jira_enabled(self) -> bool:
        return bool(self.jira_base_url and self.jira_api_token)

    @property
    def slack_enabled(self) -> bool:
        return bool(self.slack_webhook_url)

    @property
    def ai_enabled(self) -> bool:
        return bool(self.anthropic_api_key)


settings = Settings()
