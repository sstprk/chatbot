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

    # ── LLM ──────────────────────────────────────────────────────
    ollama_url: str = "http://mnemo-ollama:11434"
    # URL of the Ollama instance. Can be any Ollama server —
    # local, remote, or shared with other services.

    ollama_model: str = "qwen2.5:3b"
    # Model to use for answer generation.
    # Must be pulled on the Ollama instance before use.

    llm_timeout: float = 120.0
    # Seconds to wait for Ollama response.

    llm_temperature: float = 0.3
    llm_max_tokens: int = 1024

    system_prompt: str = (
        "You are a helpful internal company assistant. "
        "Answer questions using ONLY the provided context from the "
        "company knowledge base. If the context does not contain "
        "enough information to answer, say so honestly. "
        "When referencing information, mention the source "
        "(channel name or document title). Be concise and professional."
    )
    # Default system prompt. Can be overridden per request.

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
