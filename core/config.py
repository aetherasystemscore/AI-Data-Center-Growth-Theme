"""Application configuration and environment management for AI3."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Any
import yaml


ROOT_DIR = Path(__file__).resolve().parent.parent
CONFIG_DIR = ROOT_DIR / "config"
DATA_STORE_DIR = ROOT_DIR / "data_store"
LOGS_DIR = ROOT_DIR / "logs"


def _load_dotenv_if_present() -> None:
    """Load key=value pairs from .env without requiring external dependencies."""
    env_path = ROOT_DIR / ".env"
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, val = line.split("=", 1)
        key = key.strip()
        val = val.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = val


_load_dotenv_if_present()


@dataclass
class AppConfig:
    """Central runtime configuration for the AI3 platform."""

    app_name: str = "AI Infrastructure Investment Intelligence (AI3)"
    version: str = "1.0.0"
    database_url: str = field(
        default_factory=lambda: os.getenv(
            "DATABASE_URL",
            f"sqlite:///{(DATA_STORE_DIR / 'ai3.db').as_posix()}",
        )
    )
    data_mode: str = field(
        default_factory=lambda: os.getenv("AI3_DATA_MODE", "HYBRID").upper()
    )
    http_timeout_seconds: int = field(
        default_factory=lambda: int(os.getenv("AI3_HTTP_TIMEOUT_SECONDS", "15"))
    )
    stale_price_days: int = field(
        default_factory=lambda: int(os.getenv("AI3_STALE_PRICE_DAYS", "5"))
    )
    stale_fundamentals_days: int = field(
        default_factory=lambda: int(os.getenv("AI3_STALE_FUNDAMENTALS_DAYS", "120"))
    )
    local_ai_only: bool = field(
        default_factory=lambda: os.getenv("AI3_LOCAL_AI_ONLY", "false").lower() == "true"
    )
    allow_portfolio_ai_sharing: bool = field(
        default_factory=lambda: os.getenv("AI3_ALLOW_PORTFOLIO_AI_SHARING", "false").lower() == "true"
    )
    deepseek_api_key: str = field(default_factory=lambda: os.getenv("DEEPSEEK_API_KEY", ""))
    deepseek_base_url: str = field(
        default_factory=lambda: os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")
    )
    deepseek_model: str = field(
        default_factory=lambda: os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
    )
    gemini_api_key: str = field(default_factory=lambda: os.getenv("GEMINI_API_KEY", ""))
    gemini_model: str = field(
        default_factory=lambda: os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
    )
    groq_api_key: str = field(default_factory=lambda: os.getenv("GROQ_API_KEY", ""))
    openai_api_key: str = field(default_factory=lambda: os.getenv("OPENAI_API_KEY", ""))
    ollama_base_url: str = field(
        default_factory=lambda: os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    )
    ollama_model: str = field(
        default_factory=lambda: os.getenv("OLLAMA_MODEL", "llama3.1:8b")
    )

    @property
    def config_dir(self) -> Path:
        return CONFIG_DIR

    @property
    def sqlite_db_path(self) -> Path:
        return DATA_STORE_DIR / "ai3.db"

    @property
    def seed_stocks_path(self) -> Path:
        return CONFIG_DIR / "seed_stocks.csv"

    @property
    def seed_etfs_path(self) -> Path:
        return CONFIG_DIR / "seed_etfs.csv"

    @property
    def seed_ipos_path(self) -> Path:
        return CONFIG_DIR / "seed_ipos.json"

    @property
    def seed_smallcases_path(self) -> Path:
        return CONFIG_DIR / "seed_smallcases.json"

    @property
    def sample_fundamentals_path(self) -> Path:
        return CONFIG_DIR / "sample_fundamentals_synthetic.csv"

    @property
    def taxonomy_path(self) -> Path:
        return CONFIG_DIR / "sector_taxonomy.yaml"

    def load_taxonomy(self) -> Dict[str, Any]:
        if not self.taxonomy_path.exists():
            return {"categories": {}}
        with self.taxonomy_path.open("r", encoding="utf-8") as fh:
            return yaml.safe_load(fh) or {"categories": {}}

    def has_any_cloud_ai_key(self) -> bool:
        if self.local_ai_only:
            return False
        return bool(
            self.gemini_api_key
            or self.deepseek_api_key
            or self.groq_api_key
            or self.openai_api_key
        )


def get_config() -> AppConfig:
    DATA_STORE_DIR.mkdir(parents=True, exist_ok=True)
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    return AppConfig()


get_settings = get_config


def load_sector_taxonomy() -> Dict[str, Any]:
    """Load the sector taxonomy YAML configuration."""
    return get_config().load_taxonomy()

