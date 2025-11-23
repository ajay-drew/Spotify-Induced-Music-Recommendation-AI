"""
Spotify integration layer for SIMRAI.

Phase 1 scope:
- Direct Web API access using Client Credentials flow.
- Strictly read-only:
  - Search for tracks/artists/genres (metadata).
  - Fetch audio features for tracks.
- Shaped so that an MCP-backed backend can be plugged in later for the same
  metadata + audio-features-only capabilities.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from time import time
from typing import Dict, List, Optional

import base64

import httpx

from .config import AppConfig, SpotifyConfig, load_config

logger = logging.getLogger(__name__)


SPOTIFY_TOKEN_URL = "https://accounts.spotify.com/api/token"
SPOTIFY_API_BASE_URL = "https://api.spotify.com/v1"


class SpotifyError(Exception):
    """Base exception for Spotify-related issues."""


class SpotifyAuthError(SpotifyError):
    """Authentication or credential problems."""


class SpotifyAPIError(SpotifyError):
    """Non-auth API errors (network, rate limit, bad responses)."""


@dataclass
class _TokenInfo:
    access_token: str
    expires_at: float

    @property
    def is_expired(self) -> bool:
        # Add a small safety margin.
        return time() >= self.expires_at - 10


class DirectSpotifyClient:
    """
    Direct Spotify Web API client using Client Credentials flow.

    This client is strictly read-only and only exposes:
    - search_tracks
    - get_audio_features
    """

    def __init__(self, cfg: SpotifyConfig, *, timeout: float = 10.0) -> None:
        self._cfg = cfg
        self._http = httpx.Client(timeout=timeout)
        self._token: Optional[_TokenInfo] = None

        # Simple in-memory caches keyed by ID.
        self._audio_features_cache: Dict[str, dict] = {}
        self._track_cache: Dict[str, dict] = {}

    # --------------------------------------------------------------------- #
    # Authentication
    # --------------------------------------------------------------------- #
    def _ensure_credentials(self) -> None:
        if not self._cfg.client_id or not self._cfg.client_secret:
            logger.error("Spotify credentials missing: client_id or client_secret not set")
            raise SpotifyAuthError(
                "Spotify client ID/secret are missing. "
                "Set SIMRAI_SPOTIFY_CLIENT_ID and SIMRAI_SPOTIFY_CLIENT_SECRET."
            )

    def _get_access_token(self) -> str:
        self._ensure_credentials()

        if self._token and not self._token.is_expired:
            logger.debug("Using cached Spotify access token")
            return self._token.access_token

        logger.info("Requesting new Spotify access token (client credentials)")
        auth_header = base64.b64encode(
            f"{self._cfg.client_id}:{self._cfg.client_secret}".encode("utf-8")
        ).decode("utf-8")

        try:
            resp = self._http.post(
                SPOTIFY_TOKEN_URL,
                data={"grant_type": "client_credentials"},
                headers={"Authorization": f"Basic {auth_header}"},
            )
        except httpx.HTTPError as exc:
            logger.error(f"Failed to contact Spotify token endpoint: {exc}")
            raise SpotifyAuthError(f"Failed to contact Spotify token endpoint: {exc}") from exc

        if resp.status_code != 200:
            logger.error(f"Spotify auth failed: {resp.status_code} {resp.text}")
            raise SpotifyAuthError(
                f"Spotify auth failed: {resp.status_code} {resp.text}"
            )

        data = resp.json()
        access_token = data.get("access_token")
        expires_in = int(data.get("expires_in", 3600))

        if not access_token:
            logger.error("Spotify token response missing access_token")
            raise SpotifyAuthError("Spotify token response missing access_token.")

        self._token = _TokenInfo(
            access_token=access_token,
            expires_at=time() + expires_in,
        )
        logger.info(f"Spotify access token obtained (expires in {expires_in}s)")
        return access_token

    # --------------------------------------------------------------------- #
    # Low-level request helper
    # --------------------------------------------------------------------- #
    def _request(self, method: str, path: str, **kwargs) -> dict:
        token = self._get_access_token()
        url = f"{SPOTIFY_API_BASE_URL}{path}"
        headers = kwargs.pop("headers", {})
        headers["Authorization"] = f"Bearer {token}"

        logger.debug(f"Spotify API request: {method} {path}")
        try:
            resp = self._http.request(method, url, headers=headers, **kwargs)
        except httpx.HTTPError as exc:
            logger.error(f"HTTP error calling Spotify API {path}: {exc}")
            raise SpotifyAPIError(f"Error calling Spotify API: {exc}") from exc

        if resp.status_code == 401:
            # Try once more with a fresh token.
            logger.warning(f"Spotify API returned 401 on {path}, retrying with fresh token")
            self._token = None
            token = self._get_access_token()
            headers["Authorization"] = f"Bearer {token}"
            try:
                resp = self._http.request(method, url, headers=headers, **kwargs)
            except httpx.HTTPError as exc:
                logger.error(f"HTTP error calling Spotify API {path} after retry: {exc}")
                raise SpotifyAPIError(f"Error calling Spotify API after retry: {exc}") from exc

        if not resp.is_success:
            logger.error(f"Spotify API error {resp.status_code} on {path}: {resp.text}")
            raise SpotifyAPIError(
                f"Spotify API error {resp.status_code} on {path}: {resp.text}"
            )

        logger.debug(f"Spotify API request successful: {method} {path} -> {resp.status_code}")
        return resp.json()

    # --------------------------------------------------------------------- #
    # Public read-only methods
    # --------------------------------------------------------------------- #
    def search_tracks(self, query: str, *, limit: int = 20) -> List[dict]:
        """
        Search for tracks by free-text query.
        """
        logger.info(f"Searching Spotify tracks: query={query!r}, limit={limit}")
        params = {
            "q": query,
            "type": "track",
            "limit": max(1, min(limit, 50)),
        }
        data = self._request("GET", "/search", params=params)
        items = data.get("tracks", {}).get("items", [])
        logger.debug(f"Spotify search returned {len(items)} tracks")
        # Cache basic track info by ID.
        for item in items:
            track_id = item.get("id")
            if track_id:
                self._track_cache[track_id] = item
        return items

    def get_audio_features(self, track_ids: List[str]) -> Dict[str, dict]:
        """
        Fetch audio features for a list of track IDs, using an in-memory cache.

        Returns a mapping {track_id: features_dict}.
        """
        # Filter IDs we don't already have cached.
        missing_ids = [tid for tid in track_ids if tid not in self._audio_features_cache]
        cached_count = len(track_ids) - len(missing_ids)
        logger.debug(f"Fetching audio features: {len(missing_ids)} new, {cached_count} cached")
        result: Dict[str, dict] = {}

        # Spotify supports up to 100 IDs per audio-features request.
        for i in range(0, len(missing_ids), 100):
            chunk = missing_ids[i : i + 100]
            if not chunk:
                continue
            params = {"ids": ",".join(chunk)}
            try:
                data = self._request("GET", "/audio-features", params=params)
            except SpotifyAPIError as exc:
                logger.error(f"Failed to fetch audio features: {exc}")
                raise
            features_list = data.get("audio_features", []) or []
            logger.debug(f"Retrieved audio features for {len(features_list)} tracks")
            for features in features_list:
                tid = features.get("id")
                if tid:
                    self._audio_features_cache[tid] = features

        # Build result from cache.
        for tid in track_ids:
            if tid in self._audio_features_cache:
                result[tid] = self._audio_features_cache[tid]

        logger.info(f"Audio features retrieved: {len(result)}/{len(track_ids)} tracks")
        return result

    def close(self) -> None:
        logger.debug("Closing DirectSpotifyClient HTTP connection")
        self._http.close()


class McpSpotifyClient:
    """
    Placeholder MCP-backed client for Spotify.

    Phase 1:
    - We only define the shape and the expectation that it will return
      the same kind of metadata and audio features as DirectSpotifyClient.
    - Actual MCP integration will be wired in a later phase.
    """

    def __init__(self, cfg: SpotifyConfig) -> None:
        self._cfg = cfg
        # Real MCP wiring to be implemented in a future phase.

    def search_tracks(self, query: str, *, limit: int = 20) -> List[dict]:
        raise NotImplementedError("MCP-based Spotify search is not implemented yet.")

    def get_audio_features(self, track_ids: List[str]) -> Dict[str, dict]:
        raise NotImplementedError("MCP-based Spotify audio features are not implemented yet.")

    def close(self) -> None:
        # Placeholder for symmetry with DirectSpotifyClient.
        return None


class SpotifyService:
    """
    High-level Spotify service abstraction for SIMRAI.

    Chooses between direct Web API and MCP backend based on configuration,
    but always exposes the same, read-only interface:
    - search_tracks
    - get_audio_features
    """

    def __init__(self, cfg: Optional[AppConfig] = None) -> None:
        if cfg is None:
            cfg = load_config()
        self._cfg = cfg

        backend: object
        spotify_cfg = cfg.spotify

        if spotify_cfg.use_mcp_first and spotify_cfg.mcp_server_url:
            logger.info(f"Using MCP Spotify backend: {spotify_cfg.mcp_server_url}")
            # For now this will raise NotImplementedError if used, but the
            # shape is ready for when MCP wiring is available.
            backend = McpSpotifyClient(spotify_cfg)
        else:
            logger.debug("Using direct Spotify Web API backend")
            backend = DirectSpotifyClient(spotify_cfg)

        self._backend = backend

    def search_tracks(self, query: str, *, limit: int = 20) -> List[dict]:
        return self._backend.search_tracks(query, limit=limit)

    def get_audio_features(self, track_ids: List[str]) -> Dict[str, dict]:
        return self._backend.get_audio_features(track_ids)

    def close(self) -> None:
        self._backend.close()


__all__ = [
    "SpotifyService",
    "SpotifyError",
    "SpotifyAuthError",
    "SpotifyAPIError",
]


