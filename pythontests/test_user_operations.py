"""
Test suite for user profile operations: /api/me, /api/unlink-spotify.
"""

import pytest
from unittest.mock import Mock, patch
from fastapi.testclient import TestClient

from simrai import api
from simrai.api import app


class TestUserProfile:
    """Test user profile endpoint (/api/me)."""

    def test_api_me_requires_authentication(self):
        """Test that /api/me requires valid session."""
        client = TestClient(app)
        resp = client.get("/api/me")
        
        assert resp.status_code == 401
        assert "No active session" in resp.json()["detail"]

    def test_api_me_returns_user_profile(self):
        """Test successful user profile retrieval."""
        with patch.object(api, '_get_user_access_token') as mock_token, \
             patch.object(api, '_oauth_http') as mock_http, \
             patch.object(api, '_sessions', {"test_session": "test_user"}):
            mock_token.return_value = "test_access_token"
            
            mock_resp = Mock()
            mock_resp.is_success = True
            mock_resp.json.return_value = {
                "id": "test_user_123",
                "display_name": "Test User",
                "images": [{"url": "https://example.com/avatar.jpg"}]
            }
            mock_http.get.return_value = mock_resp
            
            client = TestClient(app)
            client.cookies.set("simrai_session", "test_session")
            resp = client.get("/api/me")
            
            assert resp.status_code == 200
            data = resp.json()
            assert data["id"] == "test_user_123"
            assert data["display_name"] == "Test User"
            assert data["avatar_url"] == "https://example.com/avatar.jpg"

    def test_api_me_handles_missing_avatar(self):
        """Test that /api/me handles missing avatar gracefully."""
        with patch.object(api, '_get_user_access_token') as mock_token, \
             patch.object(api, '_oauth_http') as mock_http, \
             patch.object(api, '_sessions', {"test_session": "test_user"}):
            mock_token.return_value = "test_access_token"
            
            mock_resp = Mock()
            mock_resp.is_success = True
            mock_resp.json.return_value = {
                "id": "test_user_123",
                "display_name": "Test User",
                "images": []
            }
            mock_http.get.return_value = mock_resp
            
            client = TestClient(app)
            client.cookies.set("simrai_session", "test_session")
            resp = client.get("/api/me")
            
            assert resp.status_code == 200
            data = resp.json()
            assert data["avatar_url"] is None

    def test_api_me_handles_spotify_error(self):
        """Test that /api/me handles Spotify API errors."""
        with patch.object(api, '_get_user_access_token') as mock_token, \
             patch.object(api, '_oauth_http') as mock_http, \
             patch.object(api, '_sessions', {"test_session": "test_user"}):
            mock_token.return_value = "test_access_token"
            
            mock_resp = Mock()
            mock_resp.is_success = False
            mock_resp.status_code = 401
            mock_resp.text = "Unauthorized"
            mock_http.get.return_value = mock_resp
            
            client = TestClient(app)
            client.cookies.set("simrai_session", "test_session")
            resp = client.get("/api/me")
            
            assert resp.status_code == 401
            assert "Spotify /me error" in resp.json()["detail"]


class TestUnlinkSpotify:
    """Test unlink Spotify endpoint (/api/unlink-spotify)."""

    def test_unlink_spotify_removes_tokens(self):
        """Test that unlink removes stored tokens and session."""
        with patch.object(api, '_delete_tokens') as mock_delete, \
             patch.object(api, '_sessions', {"test_session": "test_user"}):
            client = TestClient(app)
            client.cookies.set("simrai_session", "test_session")
            resp = client.post("/api/unlink-spotify")
            
            assert resp.status_code == 200
            data = resp.json()
            assert data["status"] == "unlinked"
            # Verify tokens were deleted
            mock_delete.assert_called_once_with("test_user")
            # Verify session was removed
            assert "test_session" not in api._sessions

    def test_unlink_spotify_clears_cookie(self):
        """Test that unlink clears the session cookie."""
        with patch.object(api, '_sessions', {"test_session": "test_user"}):
            client = TestClient(app)
            client.cookies.set("simrai_session", "test_session")
            resp = client.post("/api/unlink-spotify")
            
            assert resp.status_code == 200
            # Check that cookie is cleared (set to empty/expired)
            set_cookie = resp.headers.get("set-cookie", "")
            assert "simrai_session" in set_cookie.lower()
            assert "max-age=0" in set_cookie.lower() or "expires=" in set_cookie.lower()

    def test_unlink_spotify_handles_no_session(self):
        """Test that unlink handles missing session gracefully."""
        with patch.object(api, '_sessions', {}):
            client = TestClient(app)
            # No session cookie
            resp = client.post("/api/unlink-spotify")
            
            # Should still return success (idempotent)
            assert resp.status_code == 200
            data = resp.json()
            assert data["status"] == "unlinked"

