from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    # --- LLM provider ---
    llm_provider: str = "groq"  # groq | openai | anthropic | azure_openai
    llm_model_groq: str = "openai/gpt-oss-120b"
    llm_model_openai: str = "gpt-4o-mini"
    llm_model_anthropic: str = "claude-sonnet-5"
    llm_temperature: float = 0.2
    llm_timeout_seconds: int = 30  # per-call network timeout — a stalled provider call must fail, not hang

    groq_api_key: str = ""
    openai_api_key: str = ""
    anthropic_api_key: str = ""

    # --- Azure OpenAI (used when llm_provider = azure_openai) ---
    azure_openai_api_key: str = ""
    azure_openai_endpoint: str = ""
    azure_openai_chat_deployment: str = ""
    azure_openai_api_version: str = "2024-08-01-preview"

    # --- Routing / classification ---
    confidence_threshold: float = 0.6  # below this -> human_review branch (AI uncertain about type)

    # --- Remediation timers ---
    complaint_followup_hours: int = 2
    service_request_sla_hours: int = 24

    # --- Department routing (Service Request branch) ---
    department_routing: dict[str, str] = {
        "billing": "Billing Team",
        "technical": "Technical Support",
        "account": "Account Management",
        "general": "General Operations",
    }

    # --- Paths ---
    db_path: Path = Path(__file__).resolve().parents[2] / "db" / "requests.db"
    sample_data_path: Path = Path(__file__).resolve().parents[2] / "data" / "sample_requests.json"

    # --- API ---
    api_host: str = "127.0.0.1"
    api_port: int = 8000


settings = Settings()
