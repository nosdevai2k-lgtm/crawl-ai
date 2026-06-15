"""Application settings from environment."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

# Wikimedia / Wikipedia reject generic bot UAs — see docs/CRAWL.md
DEFAULT_USER_AGENT = (
    "crawl-ai/1.0 (+https://github.com/user/crawl-ai; crawl-ai-bot) httpx/0.28"
)


@dataclass
class Settings:
    ollama_base_url: str
    ollama_model: str
    ollama_api_key: str
    http_timeout: float
    user_agent: str
    database_path: Path
    max_text_chars: int
    llm_max_retries: int
    llm_retry_backoff_sec: float
    skip_llm: bool
    mongodb_uri: str | None
    mongodb_database: str
    mongodb_collection: str
    image_download_dir: Path = Path("data/images")
    video_kg_base_url: str = ""


def load_settings(env_path: Path | None = None) -> Settings:
    if env_path and env_path.is_file():
        load_dotenv(env_path)
    else:
        load_dotenv()

    db = Path(os.environ.get("DATABASE_PATH", "data/crawl.db"))
    if not db.is_absolute():
        db = Path.cwd() / db

    mongo_uri = (os.environ.get("MONGODB_URI") or "").strip()
    mongo_db = (os.environ.get("MONGODB_DATABASE") or "crawl_ai").strip()
    mongo_coll = (os.environ.get("MONGODB_COLLECTION") or "documents").strip()

    return Settings(
        ollama_base_url=(
            os.environ.get("LLM_BASE_URL")
            or os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434/v1")
        ).rstrip("/"),
        ollama_model=os.environ.get("LLM_MODEL") or os.environ.get("OLLAMA_MODEL", "qwen2.5:7b"),
        ollama_api_key=os.environ.get("LLM_API_KEY") or os.environ.get("OLLAMA_API_KEY", "ollama"),
        http_timeout=float(os.environ.get("HTTP_TIMEOUT", "60")),
        user_agent=os.environ.get("USER_AGENT", DEFAULT_USER_AGENT),
        database_path=db,
        max_text_chars=int(os.environ.get("MAX_TEXT_CHARS", "40000")),
        llm_max_retries=int(os.environ.get("LLM_MAX_RETRIES", "3")),
        llm_retry_backoff_sec=float(os.environ.get("LLM_RETRY_BACKOFF_SEC", "2")),
        skip_llm=os.environ.get("SKIP_LLM", "").lower() in ("1", "true", "yes"),
        mongodb_uri=mongo_uri or None,
        mongodb_database=mongo_db,
        mongodb_collection=mongo_coll,
        image_download_dir=Path(os.environ.get("IMAGE_DOWNLOAD_DIR", "data/images")),
        video_kg_base_url=(os.environ.get("VIDEO_KG_BASE_URL") or "").strip().rstrip("/"),
    )
