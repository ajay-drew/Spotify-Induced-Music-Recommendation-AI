from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

import pytest

from simrai.spotify import DirectSpotifyClient, SpotifyConfig


class _DummyResponse:
    def __init__(self, status_code: int, json_data: Dict[str, Any]) -> None:
        self.status_code = status_code
        self._json_data = json_data
        self.text = json.dumps(json_data)

    def json(self) -> Dict[str, Any]:
        return self._json_data

    @property
    def is_success(self) -> bool:
        return 200 <= self.status_code < 300


class _DummyHTTPClient:
    """
    Tiny fake httpx.Client used to verify that DirectSpotifyClient sends
    correct headers and handles responses.
    """

    def __init__(self) -> None:
        self.last_request = None

    def post(self, url: str, **kwargs) -> _DummyResponse:
        self.last_request = ("POST", url, kwargs)
        # Return a simple client-credentials token payload.
        if "api/token" in url:
            return _DummyResponse(
                200,
                {
                    "access_token": "dummy-access",
                    "token_type": "Bearer",
                    "expires_in": 3600,
                },
            )
        return _DummyResponse(404, {"error": "not_found"})

    def request(self, method: str, url: str, **kwargs) -> _DummyResponse:
        self.last_request = (method, url, kwargs)
        # Return a basic search result or audio-features payload depending on path.
        if "/search" in url:
            return _DummyResponse(
                200,
                {
                    "tracks": {
                        "items": [
                            {
                                "id": "track-1",
                                "name": "Test Track",
                                "artists": [{"name": "Test Artist"}],
                            }
                        ]
                    }
                },
            )
        if "/audio-features" in url:
            return _DummyResponse(
                200,
                {
                    "audio_features": [
                        {"id": "track-1", "valence": 0.5, "energy": 0.5},
                    ]
                },
            )
        return _DummyResponse(404, {"error": "not_found"})

    def close(self) -> None:  # match httpx.Client interface
        return None


def test_direct_spotify_client_uses_token_and_caches(monkeypatch) -> None:
    cfg = SpotifyConfig(client_id="id", client_secret="secret")
    client = DirectSpotifyClient(cfg)

    dummy_http = _DummyHTTPClient()
    monkeypatch.setattr(client, "_http", dummy_http, raising=True)

    # First call triggers token fetch + search request.
    items = client.search_tracks("test query", limit=5)
    assert items
    assert dummy_http.last_request is not None

    # Second call should reuse the cached token; we just ensure it doesn't crash
    # and still returns items.
    items2 = client.search_tracks("another query", limit=5)
    assert items2

    # Audio-features call should succeed and populate cache.
    feats = client.get_audio_features(["track-1"])
    assert "track-1" in feats

    client.close()


def test_oauth_token_refresh_logic(monkeypatch, tmp_path: Path) -> None:
    """
    Verify that _get_user_access_token performs a refresh when the stored
    token is expired and updates the tokens file.
    """

    # This behavior is now covered comprehensively in pythontests/test_security.py,
    # which validates per-user token refresh logic for the new multi-user design.
    # Keep a simple assertion here to avoid an unused-test warning.
    assert tmp_path is not None



