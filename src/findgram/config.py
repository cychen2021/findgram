"""Configuration management for findgram."""

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    import tomllib
except ImportError:
    import tomli as tomllib  # type: ignore


@dataclass
class SessionConfig:
    """Configuration for a single Telegram session."""

    name: str
    telegram_id: int
    included_chats: list[int | str]  # Support both IDs and usernames


@dataclass
class MeiliSearchConfig:
    """MeiliSearch configuration."""

    memory_limit: str = "512MB"
    host: str = "http://localhost:7700"
    master_key: str | None = None


@dataclass
class Config:
    """Main application configuration."""

    app_id: int
    app_hash: str
    app_token: str
    sessions: list[SessionConfig]
    meilisearch: MeiliSearchConfig


def get_config_dir() -> Path:
    """Get the configuration directory, respecting XDG_CONFIG_HOME."""
    xdg_config = os.environ.get("XDG_CONFIG_HOME")
    if xdg_config:
        config_dir = Path(xdg_config) / "findgram"
    else:
        config_dir = Path.home() / ".config" / "findgram"

    config_dir.mkdir(parents=True, exist_ok=True)
    return config_dir


def get_data_dir() -> Path:
    """Get the data directory, respecting XDG_DATA_HOME."""
    xdg_data = os.environ.get("XDG_DATA_HOME")
    if xdg_data:
        data_dir = Path(xdg_data) / "findgram"
    else:
        data_dir = Path.home() / ".local" / "share" / "findgram"

    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir


def load_config() -> Config:
    """Load configuration from config.toml and secrets.toml."""
    config_dir = get_config_dir()

    # Load main config
    config_path = config_dir / "config.toml"
    if not config_path.exists():
        raise FileNotFoundError(
            f"Configuration file not found at {config_path}. "
            "Please create config.toml with app_id, app_hash, and session configurations."
        )

    with open(config_path, "rb") as f:
        config_data = tomllib.load(f)

    # Load secrets
    secrets_path = config_dir / "secrets.toml"
    if not secrets_path.exists():
        raise FileNotFoundError(
            f"Secrets file not found at {secrets_path}. "
            "Please create secrets.toml with app_token."
        )

    with open(secrets_path, "rb") as f:
        secrets_data = tomllib.load(f)

    # Parse MeiliSearch config
    meilisearch_data = config_data.get("meilisearch", {})
    meilisearch = MeiliSearchConfig(
        memory_limit=meilisearch_data.get("memory_limit", "512MB"),
        host=meilisearch_data.get("host", "http://localhost:7700"),
        master_key=secrets_data.get("master_key"),
    )

    # Parse sessions
    sessions = []
    for session_data in config_data.get("sessions", []):
        sessions.append(
            SessionConfig(
                name=session_data["name"],
                telegram_id=session_data["telegram_id"],
                included_chats=session_data["included_chats"],
            )
        )

    if not sessions:
        raise ValueError("At least one session must be configured in config.toml")

    return Config(
        app_id=config_data["app_id"],
        app_hash=config_data["app_hash"],
        app_token=secrets_data["app_token"],
        sessions=sessions,
        meilisearch=meilisearch,
    )
