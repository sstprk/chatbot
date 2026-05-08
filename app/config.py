"""
Application configuration via pydantic-settings.
All values are loaded from environment variables / .env file.
"""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # ── Slack ────────────────────────────────────────────────────────
    slack_bot_token: str
    slack_signing_secret: str
    slack_channels_to_ingest: str = ""  # comma-separated channel names

    # ── Notion ───────────────────────────────────────────────────────
    notion_integration_token: str = ""
    notion_page_ids: str = ""  # comma-separated page IDs

    # ── Ollama ───────────────────────────────────────────────────────
    ollama_base_url: str = "http://ollama:11434"
    ollama_model: str = "qwen2.5:3b"
    ollama_embed_model: str = "nomic-embed-text"

    # ── Qdrant ───────────────────────────────────────────────────────
    qdrant_url: str = "http://qdrant:6333"
    qdrant_collection: str = "company_knowledge"

    # ── Ingestion ────────────────────────────────────────────────────
    ingestion_interval_minutes: int = 60

    # ── App ──────────────────────────────────────────────────────────
    app_host: str = "0.0.0.0"
    app_port: int = 8000

    # ── Helpers ──────────────────────────────────────────────────────
    @property
    def slack_channels_list(self) -> list[str]:
        """Return list of Slack channels to ingest."""
        if not self.slack_channels_to_ingest:
            return []
        return [ch.strip() for ch in self.slack_channels_to_ingest.split(",") if ch.strip()]

    @property
    def notion_page_ids_list(self) -> list[str]:
        """Return list of Notion page IDs to ingest."""
        if not self.notion_page_ids:
            return []
        return [pid.strip() for pid in self.notion_page_ids.split(",") if pid.strip()]

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


# Singleton settings instance
settings = Settings()
