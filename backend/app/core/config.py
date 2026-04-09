from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # App
    APP_NAME: str = "AgentX SRE-Triage"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False

    # Database
    DATABASE_URL: str = "postgresql://sre_user:sre_pass@db:5432/sre_triage"

    # AI
    GEMINI_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-2.5-flash"
    GEMINI_FALLBACK_MODEL: str = "gemini-2.0-flash"

    # Langfuse Observability
    LANGFUSE_PUBLIC_KEY: str = ""
    LANGFUSE_SECRET_KEY: str = ""
    LANGFUSE_BASE_URL: str = "https://us.cloud.langfuse.com"

    # Mocked integrations
    SLACK_WEBHOOK_URL: str = "http://mock-slack/webhook"
    JIRA_PROJECT_KEY: str = "SRE"
    NOTIFY_EMAIL_FROM: str = "sre-agent@company.com"
    SRE_TEAM_EMAIL: str = "sre-team@company.com"
    SRE_SLACK_CHANNEL: str = "#sre-alerts"

    # Uploads
    UPLOAD_DIR: str = "/app/uploads"
    MAX_FILE_SIZE_MB: int = 20

    # Security
    GUARDRAIL_STRICT: bool = True
    MAX_DESCRIPTION_LENGTH: int = 5000

    # eShop context
    ESHOP_CONTEXT_PATH: str = "/app/context-provider/ecommerce-repo/src"

    class Config:
        env_file = ".env"
        case_sensitive = True
        extra = "ignore"


@lru_cache()
def get_settings() -> Settings:
    return Settings()
