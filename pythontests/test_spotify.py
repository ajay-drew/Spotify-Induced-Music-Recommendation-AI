from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

import pytest

from simrai.api import _get_user_access_token, _save_tokens, _tokens_path
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

    # Prepare a fake tokens file with an already-expired access token.
    expired_tokens_path = tmp_path / "spotify_oauth.json"
    # Use a small positive expires_at so the token is considered structurally
    # valid but clearly expired compared to current time.time().
    tokens = {
        "access_token": "old-token",
        "refresh_token": "refresh-token",
        "expires_at": 1,
    }
    expired_tokens_path.write_text(json.dumps(tokens), encoding="utf-8")

    # Point the internal _tokens_path used by simrai.api to our temp file.
    monkeypatch.setattr("simrai.api._tokens_path", expired_tokens_path, raising=True)

    # Fake configuration with client credentials.
    from simrai import api as api_mod

    api_mod._cfg.spotify.client_id = "client-id"
    api_mod._cfg.spotify.client_secret = "client-secret"

    class _DummyOAuthHTTP:
        def post(self, url: str, data=None, auth=None):  # noqa: D401, ARG002
            # Always return a new token.
            return _DummyResponse(
                200,
                {
                    "access_token": "new-token",
                    "token_type": "Bearer",
                    "expires_in": 3600,
                },
            )

    monkeypatch.setattr("simrai.api._oauth_http", _DummyOAuthHTTP(), raising=True)

    # Call helper: it should perform a refresh and return the new token.
    token = _get_user_access_token()
    assert token == "new-token"

    # Ensure the tokens file was updated.
    updated = json.loads(expired_tokens_path.read_text(encoding="utf-8"))
    assert updated["access_token"] == "new-token"
    assert updated["expires_at"] > 0



