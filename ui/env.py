"""Environment bootstrap for Streamlit."""

from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv


def reload_env(root: Path) -> None:
    env_file = root / ".env"
    if env_file.is_file():
        load_dotenv(env_file, override=True)
    else:
        load_dotenv(override=False)
