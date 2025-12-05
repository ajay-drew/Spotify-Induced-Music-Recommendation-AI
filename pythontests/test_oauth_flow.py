"""
Comprehensive test suite for OAuth flow: login, callback, token management.
"""

import pytest
import time
import secrets
import os
from unittest.mock import Mock, patch, MagicMock
from fastapi.testclient import TestClient

from simrai import api
from simrai.api import app


class TestOAuthLogin:
    """Test OAuth login endpoint."""

    def test_auth_login_redirects_to_spotify(self):
        """Test that /auth/login redirects to Spotify authorization page."""
        with patch.object(api, '_cfg') as mock_cfg:
            mock_cfg.spotify.client_id = "test_client_id"
            
            client = TestClient(app)
            resp = client.get("/auth/login", follow_redirects=False)
            
            assert resp.status_code == 302
            assert "accounts.spotify.com/authorize" in resp.headers["location"]
            assert "client_id=test_client_id" in resp.headers["location"]
            assert "redirect_uri" in resp.headers["location"]
            assert "state" in resp.headers["location"]
            assert "show_dialog=true" in resp.headers["location"]

    def test_auth_login_requires_client_id(self):
        """Test that /auth/login fails if client ID is missing."""
        with patch.object(api, '_cfg') as mock_cfg:
            mock_cfg.spotify.client_id = None
            
            client = TestClient(app)
            resp = client.get("/auth/login")
            
            assert resp.status_code == 500
            assert "SIMRAI_SPOTIFY_CLIENT_ID" in resp.json()["detail"]

    def test_auth_login_generates_unique_state(self):
        """Test that each login generates a unique state token."""
        with patch.object(api, '_cfg') as mock_cfg:
            mock_cfg.spotify.client_id = "test_client_id"
            
            # Clear existing states
            api._oauth_states.clear()
            
            client = TestClient(app)
            resp1 = client.get("/auth/login", follow_redirects=False)
            resp2 = client.get("/auth/login", follow_redirects=False)
            
            # Extract state from redirect URLs
            location1 = resp1.headers["location"]
            location2 = resp2.headers["location"]
            
            # States should be different
            assert location1 != location2
            # Both should have state parameters
            assert "state=" in location1
            assert "state=" in location2

    def test_auth_login_uses_environment_redirect_uri(self):
        """Test that redirect URI can be set via environment variable."""
        with patch.object(api, '_cfg') as mock_cfg, \
             patch.dict('os.environ', {'SIMRAI_SPOTIFY_REDIRECT_URI': 'https://custom.com/callback'}):
            mock_cfg.spotify.client_id = "test_client_id"
            
            client = TestClient(app)
            resp = client.get("/auth/login", follow_redirects=False)
            
            assert resp.status_code == 302
            assert "redirect_uri=https%3A%2F%2Fcustom.com%2Fcallback" in resp.headers["location"]

    def test_auth_login_includes_required_scopes(self):
        """Test that required scopes are included in authorization URL."""
        with patch.object(api, '_cfg') as mock_cfg:
            mock_cfg.spotify.client_id = "test_client_id"
            
            client = TestClient(app)
            resp = client.get("/auth/login", follow_redirects=False)
            
            assert resp.status_code == 302
            location = resp.headers["location"]
            assert "playlist-modify-private" in location
            assert "playlist-modify-public" in location


class TestOAuthCallback:
    """Test OAuth callback endpoint."""

    def test_auth_callback_rejects_missing_code(self):
        """Test that callback rejects requests without authorization code."""
        client = TestClient(app)
        resp = client.get("/auth/callback")
        
        assert resp.status_code == 200  # Returns HTML error page
        assert "Connection Error" in resp.text
        assert "No authorization code" in resp.text

    def test_auth_callback_rejects_invalid_state(self):
        """Test that callback rejects invalid state (CSRF protection)."""
        client = TestClient(app)
        resp = client.get("/auth/callback?code=test_code&state=invalid_state")
        
        assert resp.status_code == 200  # Returns HTML error page
        assert "Security Error" in resp.text
        assert "Invalid OAuth state" in resp.text

    def test_auth_callback_handles_user_denial(self):
        """Test that callback handles user denial gracefully."""
        client = TestClient(app)
        resp = client.get("/auth/callback?error=access_denied&error_description=User%20denied")
        
        assert resp.status_code == 200  # Returns HTML error page
        assert "Connection Denied" in resp.text
        assert "access_denied" in resp.text

    def test_auth_callback_requires_client_credentials(self):
        """Test that callback requires Spotify client credentials."""
        with patch.object(api, '_cfg') as mock_cfg:
            mock_cfg.spotify.client_id = None
            mock_cfg.spotify.client_secret = None
            
            # Create valid state
            state = secrets.token_urlsafe(32)
            api._oauth_states[state] = time.time()
            
            client = TestClient(app)
            resp = client.get(f"/auth/callback?code=test_code&state={state}")
            
            assert resp.status_code == 500
            assert "client ID/secret" in resp.json()["detail"]

    def test_auth_callback_exchanges_code_for_tokens(self):
        """Test successful token exchange flow."""
        with patch.object(api, '_cfg') as mock_cfg, \
             patch.object(api, '_oauth_http') as mock_http:
            mock_cfg.spotify.client_id = "test_client_id"
            mock_cfg.spotify.client_secret = "test_secret"
            
            # Create valid state
            state = secrets.token_urlsafe(32)
            api._oauth_states[state] = time.time()
            
            # Mock token exchange response
            mock_token_resp = Mock()
            mock_token_resp.status_code = 200
            mock_token_resp.json.return_value = {
                "access_token": "test_access_token",
                "refresh_token": "test_refresh_token",
                "expires_in": 3600,
                "token_type": "Bearer",
                "scope": "playlist-modify-private playlist-modify-public"
            }
            
            # Mock user profile response
            mock_me_resp = Mock()
            mock_me_resp.is_success = True
            mock_me_resp.json.return_value = {
                "id": "test_user_id",
                "display_name": "Test User",
                "images": []
            }
            
            mock_http.post.return_value = mock_token_resp
            mock_http.get.return_value = mock_me_resp
            
            # Mock token storage
            with patch.object(api, '_save_tokens') as mock_save, \
                 patch.object(api, '_sessions', {}):
                client = TestClient(app)
                resp = client.get(f"/auth/callback?code=test_code&state={state}")
                
                assert resp.status_code == 200
                assert "Spotify Connected" in resp.text
                # Verify token exchange was called
                mock_http.post.assert_called_once()
                # Verify tokens were saved
                mock_save.assert_called_once()

    def test_auth_callback_handles_token_exchange_failure(self):
        """Test that callback handles token exchange failures."""
        with patch.object(api, '_cfg') as mock_cfg, \
             patch.object(api, '_oauth_http') as mock_http:
            mock_cfg.spotify.client_id = "test_client_id"
            mock_cfg.spotify.client_secret = "test_secret"
            
            # Create valid state
            state = secrets.token_urlsafe(32)
            api._oauth_states[state] = time.time()
            
            # Mock failed token exchange
            mock_resp = Mock()
            mock_resp.status_code = 400
            mock_resp.text = "Invalid grant"
            mock_http.post.return_value = mock_resp
            
            client = TestClient(app)
            resp = client.get(f"/auth/callback?code=test_code&state={state}")
            
            assert resp.status_code == 200  # Returns HTML error page
            assert "Connection Error" in resp.text
            assert "Failed to exchange" in resp.text


class TestTokenManagement:
    """Test token storage and retrieval."""

    def test_get_user_access_token_requires_valid_session(self):
        """Test that accessing user token requires valid session."""
        client = TestClient(app)
        resp = client.get("/api/me")
        
        assert resp.status_code == 401
        assert "No active session" in resp.json()["detail"]

    def test_get_user_access_token_refreshes_expired_tokens(self):
        """Test that expired tokens are automatically refreshed."""
        with patch.object(api, '_cfg') as mock_cfg, \
             patch.object(api, '_load_tokens') as mock_load, \
             patch.object(api, '_save_tokens') as mock_save, \
             patch.object(api, '_oauth_http') as mock_http, \
             patch.object(api, '_sessions', {"test_session": "test_user"}):
            mock_cfg.spotify.client_id = "test_client_id"
            mock_cfg.spotify.client_secret = "test_secret"
            
            # Mock expired tokens
            mock_load.return_value = {
                "access_token": "old_token",
                "refresh_token": "test_refresh_token",
                "expires_at": time.time() - 100,  # Expired
            }
            
            # Mock refresh response
            mock_refresh_resp = Mock()
            mock_refresh_resp.status_code = 200
            mock_refresh_resp.json.return_value = {
                "access_token": "new_token",
                "expires_in": 3600
            }
            mock_http.post.return_value = mock_refresh_resp
            
            # Mock /me response
            mock_me_resp = Mock()
            mock_me_resp.is_success = True
            mock_me_resp.json.return_value = {
                "id": "test_user",
                "display_name": "Test User",
                "images": []
            }
            mock_http.get.return_value = mock_me_resp
            
            client = TestClient(app)
            client.cookies.set("simrai_session", "test_session")
            resp = client.get("/api/me")
            
            assert resp.status_code == 200
            # Verify refresh was called
            mock_http.post.assert_called_once()
            # Verify new tokens were saved
            mock_save.assert_called_once()

