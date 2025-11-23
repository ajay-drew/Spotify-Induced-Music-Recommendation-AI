"""
Configuration loading for SIMRAI.

Phase 0: only defines the configuration model and where configuration will live.
Actual Spotify keys and MCP endpoints will be wired in later phases.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from platformdirs import user_config_dir
from dotenv import load_dotenv
import os
import logging
from logging.handlers import RotatingFileHandler


APP_NAME = "simrai"
APP_AUTHOR = "Project57"


@dataclass
class SpotifyConfig:
    client_id: str
    client_secret: str
    mcp_server_url: Optional[str] = None  # Optional: use Spotify via MCP instead of direct Web API.
    use_mcp_first: bool = False  # If True and mcp_server_url is set, prefer MCP over direct Web API.
    redirect_uri: Optional[str] = None  # Optional: OAuth redirect URI for user-level flows.


@dataclass
class AppConfig:
    spotify: SpotifyConfig


def get_default_config_dir() -> Path:
    """
    Returns the platform-appropriate directory for persistent SIMRAI config.
    """
    return Path(user_config_dir(APP_NAME, APP_AUTHOR))


def load_config() -> AppConfig:
    """
    Load configuration from environment variables / .env file.

    Phase 0: keep this minimal; later phases may add TOML/JSON config files.
    """
    # Load from a .env file in the project root or current directory, if present.
    load_dotenv()

    client_id = os.getenv("SIMRAI_SPOTIFY_CLIENT_ID", "")
    client_secret = os.getenv("SIMRAI_SPOTIFY_CLIENT_SECRET", "")
    mcp_server_url = os.getenv("SIMRAI_SPOTIFY_MCP_SERVER_URL")
    redirect_uri = os.getenv("SIMRAI_SPOTIFY_REDIRECT_URI")
    use_mcp_first = os.getenv("SIMRAI_SPOTIFY_USE_MCP_FIRST", "false").lower() in {"1", "true", "yes"}

    if not client_id or not client_secret:
        # For now we don't raise, because early phases may run without real credentials.
        # Later, the CLI will surface a friendly setup message if these are missing.
        pass

    spotify_cfg = SpotifyConfig(
        client_id=client_id,
        client_secret=client_secret,
        mcp_server_url=mcp_server_url,
        use_mcp_first=use_mcp_first,
        redirect_uri=redirect_uri,
    )
    return AppConfig(spotify=spotify_cfg)


def setup_logging() -> None:
    """
    Configure centralized logging for SIMRAI using Python's built-in logging module.
    
    - Logs to ~/.simrai/logs/simrai.log
    - Uses RotatingFileHandler with 10MB max size and 5 backup files
    - Logs to both file and console
    - Format: "%(asctime)s | %(levelname)-8s | %(name)s:%(funcName)s:%(lineno)d | %(message)s"
    - Default level: INFO (can be overridden via SIMRAI_LOG_LEVEL env var)
    """
    # Get log level from environment variable, default to INFO
    log_level_str = os.getenv("SIMRAI_LOG_LEVEL", "INFO").upper()
    log_level = getattr(logging, log_level_str, logging.INFO)
    
    # Get log directory
    config_dir = get_default_config_dir()
    log_dir = config_dir / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    
    # Log format
    log_format = "%(asctime)s | %(levelname)-8s | %(name)s:%(funcName)s:%(lineno)d | %(message)s"
    date_format = "%Y-%m-%d %H:%M:%S"
    
    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)
    
    # Remove existing handlers to avoid duplicates
    root_logger.handlers.clear()
    
    # File handler with rotation
    log_file = log_dir / "simrai.log"
    file_handler = RotatingFileHandler(
        str(log_file),
        maxBytes=10 * 1024 * 1024,  # 10MB
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setLevel(log_level)
    file_handler.setFormatter(logging.Formatter(log_format, date_format))
    root_logger.addHandler(file_handler)
    
    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(log_level)
    console_handler.setFormatter(logging.Formatter(log_format, date_format))
    root_logger.addHandler(console_handler)


# Initialize logging when module is imported (after get_default_config_dir is defined)
setup_logging()

__all__ = ["AppConfig", "SpotifyConfig", "get_default_config_dir", "load_config"]


