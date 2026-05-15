import logging

from pydantic_settings import BaseSettings

logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    # ── Slack ────────────────────────────────────────────────────
    slack_bot_token: str
    slack_signing_secret: str
    slack_app_token: str = ""

    # ── User Container ───────────────────────────────────────────
    container_url: str = "http://mnemo-chatbot:8000"
    user_api_key: str = ""

    # ── Bot behaviour ────────────────────────────────────────────
    bot_name: str = "Mnemo"
    query_timeout: float = 120.0
    show_sources: bool = True
    show_provenance: bool = False
    typing_emoji: str = "hourglass_flowing_sand"
    error_message: str = "Sorry, I couldn't process your request. Please try again."

    # ── App ──────────────────────────────────────────────────────
    app_host: str = "0.0.0.0"
    app_port: int = 3000
    log_level: str = "INFO"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
