"""
Test suite for playlist operations: create, add tracks, error handling.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from fastapi.testclient import TestClient

from simrai import api
from simrai.api import app, PlaylistStatsOut, PlaylistEventOut


class TestCreatePlaylist:
    """Test playlist creation endpoint."""

    def test_create_playlist_requires_authentication(self):
        """Test that creating a playlist requires valid session."""
        client = TestClient(app)
        resp = client.post("/api/create-playlist", json={"name": "Test Playlist"})
        
        assert resp.status_code == 401
        assert "No active session" in resp.json()["detail"]

    def test_create_playlist_success(self):
        """Test successful playlist creation."""
        with patch.object(api, '_cfg') as mock_cfg, \
             patch.object(api, '_get_user_access_token') as mock_token, \
             patch.object(api, '_oauth_http') as mock_http, \
             patch.object(api, '_sessions', {"test_session": "test_user"}), \
             patch.object(api, '_record_playlist_event') as mock_record:
            mock_cfg.spotify.client_id = "test_client_id"
            mock_token.return_value = "test_access_token"
            
            # Mock /me response
            mock_me_resp = Mock()
            mock_me_resp.is_success = True
            mock_me_resp.json.return_value = {"id": "test_user"}
            
            # Mock playlist creation response
            mock_playlist_resp = Mock()
            mock_playlist_resp.is_success = True
            mock_playlist_resp.json.return_value = {
                "id": "playlist_123",
                "external_urls": {"spotify": "https://open.spotify.com/playlist/123"}
            }
            
            mock_http.get.return_value = mock_me_resp
            mock_http.post.return_value = mock_playlist_resp
            
            client = TestClient(app)
            client.cookies.set("simrai_session", "test_session")
            resp = client.post(
                "/api/create-playlist",
                json={"name": "My Playlist", "description": "Test", "public": False}
            )
            
            assert resp.status_code == 200
            data = resp.json()
            assert data["playlist_id"] == "playlist_123"
            assert "spotify.com/playlist" in data["url"]

            # Verify stats recording was called best-effort
            mock_record.assert_called_once()
            args, kwargs = mock_record.call_args
            assert kwargs.get("playlist_id") == "playlist_123"
            assert kwargs.get("playlist_name") == "My Playlist"

    def test_create_playlist_uses_default_name(self):
        """Test that playlist uses default name if not provided."""
        with patch.object(api, '_cfg') as mock_cfg, \
             patch.object(api, '_get_user_access_token') as mock_token, \
             patch.object(api, '_oauth_http') as mock_http, \
             patch.object(api, '_sessions', {"test_session": "test_user"}):
            mock_cfg.spotify.client_id = "test_client_id"
            mock_token.return_value = "test_access_token"
            
            mock_me_resp = Mock()
            mock_me_resp.is_success = True
            mock_me_resp.json.return_value = {"id": "test_user"}
            
            mock_playlist_resp = Mock()
            mock_playlist_resp.is_success = True
            mock_playlist_resp.json.return_value = {
                "id": "playlist_123",
                "external_urls": {"spotify": "https://open.spotify.com/playlist/123"}
            }
            
            mock_http.get.return_value = mock_me_resp
            mock_http.post.return_value = mock_playlist_resp
            
            client = TestClient(app)
            client.cookies.set("simrai_session", "test_session")
            resp = client.post("/api/create-playlist", json={})
            
            assert resp.status_code == 200
            # Verify default name was used
            call_args = mock_http.post.call_args
            assert "SIMRAI Playlist" in str(call_args)

    def test_create_playlist_handles_spotify_error(self):
        """Test that playlist creation handles Spotify API errors."""
        with patch.object(api, '_cfg') as mock_cfg, \
             patch.object(api, '_get_user_access_token') as mock_token, \
             patch.object(api, '_oauth_http') as mock_http, \
             patch.object(api, '_sessions', {"test_session": "test_user"}):
            mock_cfg.spotify.client_id = "test_client_id"
            mock_token.return_value = "test_access_token"
            
            mock_me_resp = Mock()
            mock_me_resp.is_success = True
            mock_me_resp.json.return_value = {"id": "test_user"}
            
            # Mock failed playlist creation
            mock_playlist_resp = Mock()
            mock_playlist_resp.is_success = False
            mock_playlist_resp.status_code = 403
            mock_playlist_resp.text = "Forbidden"
            
            mock_http.get.return_value = mock_me_resp
            mock_http.post.return_value = mock_playlist_resp
            
            client = TestClient(app)
            client.cookies.set("simrai_session", "test_session")
            resp = client.post("/api/create-playlist", json={"name": "Test"})
            
            assert resp.status_code == 403
            assert "Spotify create playlist error" in resp.json()["detail"]


class TestAddTracks:
    """Test add tracks to playlist endpoint."""

    def test_add_tracks_requires_authentication(self):
        """Test that adding tracks requires valid session."""
        client = TestClient(app)
        resp = client.post(
            "/api/add-tracks",
            json={"playlist_id": "playlist_123", "uris": ["spotify:track:abc"]}
        )
        
        assert resp.status_code == 401
        assert "No active session" in resp.json()["detail"]

    def test_add_tracks_success(self):
        """Test successful track addition."""
        with patch.object(api, '_get_user_access_token') as mock_token, \
             patch.object(api, '_oauth_http') as mock_http, \
             patch.object(api, '_sessions', {"test_session": "test_user"}):
            mock_token.return_value = "test_access_token"
            
            mock_resp = Mock()
            mock_resp.is_success = True
            mock_resp.json.return_value = {"snapshot_id": "snapshot_123"}
            mock_http.post.return_value = mock_resp
            
            client = TestClient(app)
            client.cookies.set("simrai_session", "test_session")
            resp = client.post(
                "/api/add-tracks",
                json={
                    "playlist_id": "playlist_123",
                    "uris": ["spotify:track:abc", "spotify:track:def"]
                }
            )
            
            assert resp.status_code == 200
            data = resp.json()
            assert data["snapshot_id"] == "snapshot_123"

    def test_add_tracks_rejects_empty_uris(self):
        """Test that adding tracks rejects empty URI list."""
        with patch.object(api, '_get_user_access_token') as mock_token, \
             patch.object(api, '_sessions', {"test_session": "test_user"}):
            # The empty check happens after token retrieval, so we need a valid token
            mock_token.return_value = "test_access_token"
            
            client = TestClient(app)
            client.cookies.set("simrai_session", "test_session")
            resp = client.post(
                "/api/add-tracks",
                json={"playlist_id": "playlist_123", "uris": []}
            )
            
            assert resp.status_code == 400
            assert "No track URIs" in resp.json()["detail"]

    def test_add_tracks_handles_spotify_error(self):
        """Test that adding tracks handles Spotify API errors."""
        with patch.object(api, '_get_user_access_token') as mock_token, \
             patch.object(api, '_oauth_http') as mock_http, \
             patch.object(api, '_sessions', {"test_session": "test_user"}):
            mock_token.return_value = "test_access_token"
            
            # Mock failed request
            mock_resp = Mock()
            mock_resp.is_success = False
            mock_resp.status_code = 404
            mock_resp.text = "Playlist not found"
            mock_http.post.return_value = mock_resp
            
            client = TestClient(app)
            client.cookies.set("simrai_session", "test_session")
            resp = client.post(
                "/api/add-tracks",
                json={"playlist_id": "invalid_playlist", "uris": ["spotify:track:abc"]}
            )
            
            assert resp.status_code == 404
            assert "Spotify add tracks error" in resp.json()["detail"]


class TestSearchEndpoint:
    """Test Spotify search proxy endpoint."""

    def test_search_requires_authentication(self):
        """Test that search requires valid session."""
        client = TestClient(app)
        resp = client.post("/api/search", json={"query": "test", "type": "track"})
        
        assert resp.status_code == 401
        assert "No active session" in resp.json()["detail"]

    def test_search_success(self):
        """Test successful search."""
        with patch.object(api, '_get_user_access_token') as mock_token, \
             patch.object(api, '_oauth_http') as mock_http, \
             patch.object(api, '_sessions', {"test_session": "test_user"}):
            mock_token.return_value = "test_access_token"
            
            mock_resp = Mock()
            mock_resp.is_success = True
            mock_resp.json.return_value = {
                "tracks": {
                    "items": [
                        {"name": "Test Track", "artists": [{"name": "Test Artist"}]}
                    ]
                }
            }
            mock_http.get.return_value = mock_resp
            
            client = TestClient(app)
            client.cookies.set("simrai_session", "test_session")
            resp = client.post(
                "/api/search",
                json={"query": "test song", "type": "track", "limit": 20}
            )
            
            assert resp.status_code == 200
            data = resp.json()
            assert "tracks" in data
            assert len(data["tracks"]["items"]) == 1

    def test_search_enforces_limit_bounds(self):
        """Test that search enforces limit bounds (1-50)."""
        with patch.object(api, '_get_user_access_token') as mock_token, \
             patch.object(api, '_oauth_http') as mock_http, \
             patch.object(api, '_sessions', {"test_session": "test_user"}):
            mock_token.return_value = "test_access_token"
            
            mock_resp = Mock()
            mock_resp.is_success = True
            mock_resp.json.return_value = {"tracks": {"items": []}}
            mock_http.get.return_value = mock_resp
            
            client = TestClient(app)
            client.cookies.set("simrai_session", "test_session")
            
            # Test limit too high (should be capped at 50)
            resp = client.post(
                "/api/search",
                json={"query": "test", "type": "track", "limit": 100}
            )
            assert resp.status_code == 200
            # Verify limit was capped
            call_args = mock_http.get.call_args
            assert call_args[1]["params"]["limit"] == 50
            
            # Test limit too low (should be raised to 1)
            resp = client.post(
                "/api/search",
                json={"query": "test", "type": "track", "limit": 0}
            )
            assert resp.status_code == 200
            call_args = mock_http.get.call_args
            assert call_args[1]["params"]["limit"] == 1


class TestAdminPlaylistStats:
    """Tests for the admin-only playlist stats endpoint."""

    def test_playlist_stats_requires_admin_token(self, monkeypatch):
        """Endpoint should return 403 without correct admin token."""
        monkeypatch.setattr(api, "ADMIN_TOKEN", "secret-token", raising=False)

        client = TestClient(app)

        # Missing header
        resp = client.get("/admin/playlist-stats")
        assert resp.status_code == 422  # missing required header

        # Wrong token
        resp = client.get("/admin/playlist-stats", headers={"X-Admin-Token": "wrong"})
        assert resp.status_code == 403

    def test_playlist_stats_success(self, monkeypatch):
        """Admin stats endpoint should return data from _fetch_playlist_stats."""
        monkeypatch.setattr(api, "ADMIN_TOKEN", "secret-token", raising=False)

        fake_stats = PlaylistStatsOut(
            total=2,
            playlists=[
                PlaylistEventOut(
                    playlist_id="pl1",
                    playlist_name="Chill Vibes",
                    created_at="2025-01-01T00:00:00Z",
                ),
                PlaylistEventOut(
                    playlist_id="pl2",
                    playlist_name="Workout Mix",
                    created_at="2025-01-02T00:00:00Z",
                ),
            ],
        )

        with patch.object(api, "_fetch_playlist_stats", return_value=fake_stats):
            client = TestClient(app)
            resp = client.get(
                "/admin/playlist-stats", headers={"X-Admin-Token": "secret-token"}
            )

            assert resp.status_code == 200
            data = resp.json()
            assert data["total"] == 2
            assert len(data["playlists"]) == 2
            assert data["playlists"][0]["playlist_name"] == "Chill Vibes"

