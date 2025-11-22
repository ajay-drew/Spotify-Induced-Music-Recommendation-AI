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


APP_NAME = "simrai"
APP_AUTHOR = "Project57"


@dataclass
class SpotifyConfig:
    client_id: str
    client_secret: str
    mcp_server_url: Optional[str] = None  # Optional: use Spotify via MCP instead of direct Web API.
    use_mcp_first: bool = False  # If True and mcp_server_url is set, prefer MCP over direct Web API.


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
    )
    return AppConfig(spotify=spotify_cfg)


__all__ = ["AppConfig", "SpotifyConfig", "get_default_config_dir", "load_config"]


