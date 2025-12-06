"""
Test suite for security features: OAuth state management, multi-user tokens, and sessions.
"""

import pytest
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
import time
import secrets

from fastapi.testclient import TestClient

from simrai import api
from simrai.api import app


class TestOAuthStateManagement:
    """Test OAuth state to prevent race conditions and CSRF attacks."""

    def test_unique_state_per_oauth_flow(self):
        """Each OAuth flow should get a unique state token."""
        with patch.object(api, '_cfg') as mock_cfg:
            mock_cfg.spotify.client_id = "test_client_id"
            mock_cfg.spotify.redirect_uri = "http://localhost:8000/auth/callback"
            
            # Simulate two concurrent OAuth flows
            response1 = api.auth_login()
            state1 = None
            for key in api._oauth_states.keys():
                state1 = key
                break
            
            response2 = api.auth_login()
            state2 = None
            for key in api._oauth_states.keys():
                if key != state1:
                    state2 = key
                    break
            
            # States should be different
            assert state1 != state2
            # Both should be in the states dict
            assert state1 in api._oauth_states
            assert state2 in api._oauth_states

    def test_oauth_state_expiry_cleanup(self):
        """Expired OAuth states should be cleaned up."""
        with patch.object(api, '_cfg') as mock_cfg:
            mock_cfg.spotify.client_id = "test_client_id"
            mock_cfg.spotify.redirect_uri = "http://localhost:8000/auth/callback"
            
            # Add an old state (11 minutes ago)
            old_state = "old_state_token"
            api._oauth_states[old_state] = time.time() - 660  # 11 minutes ago
            
            # Trigger login (which cleans up expired states)
            response = api.auth_login()
            
            # Old state should be removed
            assert old_state not in api._oauth_states

    def test_oauth_callback_rejects_invalid_state(self):
        """OAuth callback should reject invalid/missing state."""
        client = TestClient(app)
        response = client.get("/auth/callback?code=test_code&state=invalid_state_123")
        
        # Should return error HTML
        assert response.status_code == 200
        assert b"Security Error" in response.content or b"Connection Error" in response.content

    def test_oauth_callback_rejects_missing_state(self):
        """OAuth callback should reject missing state."""
        client = TestClient(app)
        response = client.get("/auth/callback?code=test_code")
        
        # Should return error HTML
        assert response.status_code == 200
        assert b"Security Error" in response.content or b"Connection Error" in response.content

    def test_oauth_state_removed_after_use(self):
        """OAuth state should be removed after successful use to prevent replay."""
        state = secrets.token_urlsafe(32)
        api._oauth_states[state] = time.time()
        
        with patch.object(api._oauth_http, 'post') as mock_post, \
             patch.object(api._oauth_http, 'get') as mock_get, \
             patch.object(api, '_cfg') as mock_cfg:
            
            mock_cfg.spotify.client_id = "test_id"
            mock_cfg.spotify.client_secret = "test_secret"
            mock_cfg.spotify.redirect_uri = "http://localhost:8000/auth/callback"
            
            # Mock token exchange
            mock_token_resp = Mock()
            mock_token_resp.status_code = 200
            mock_token_resp.json.return_value = {
                "access_token": "test_access_token",
                "refresh_token": "test_refresh_token",
                "expires_in": 3600,
            }
            
            # Mock /me endpoint
            mock_me_resp = Mock()
            mock_me_resp.is_success = True
            mock_me_resp.json.return_value = {"id": "test_user_123"}
            
            mock_post.return_value = mock_token_resp
            mock_get.return_value = mock_me_resp
            
            # Call callback via HTTP to exercise full FastAPI path
            client = TestClient(app)
            response = client.get(f"/auth/callback?code=test_code&state={state}")
            
            # State should be removed
            assert state not in api._oauth_states


class TestMultiUserTokenStorage:
    """Test per-user token storage to support concurrent users."""

    def test_tokens_stored_per_user(self, tmp_path):
        """Tokens should be stored in separate files per user."""
        with patch.object(api, '_tokens_dir', tmp_path):
            user1_id = "spotify_user_alice"
            user2_id = "spotify_user_bob"
            
            tokens1 = {"access_token": "token_alice", "refresh_token": "refresh_alice"}
            tokens2 = {"access_token": "token_bob", "refresh_token": "refresh_bob"}
            
            # Save tokens for both users
            api._save_tokens(user1_id, tokens1)
            api._save_tokens(user2_id, tokens2)
            
            # Both files should exist
            assert (tmp_path / f"{user1_id}.json").exists()
            assert (tmp_path / f"{user2_id}.json").exists()
            
            # Load and verify
            loaded1 = api._load_tokens(user1_id)
            loaded2 = api._load_tokens(user2_id)
            
            assert loaded1["access_token"] == "token_alice"
            assert loaded2["access_token"] == "token_bob"

    def test_user_tokens_do_not_overwrite(self, tmp_path):
        """User B's tokens should not overwrite User A's tokens."""
        with patch.object(api, '_tokens_dir', tmp_path):
            user_a = "user_a"
            user_b = "user_b"
            
            # User A saves tokens
            api._save_tokens(user_a, {"access_token": "token_a"})
            
            # User B saves tokens
            api._save_tokens(user_b, {"access_token": "token_b"})
            
            # User A's tokens should still be intact
            tokens_a = api._load_tokens(user_a)
            assert tokens_a["access_token"] == "token_a"

    def test_delete_user_tokens(self, tmp_path):
        """Should be able to delete tokens for a specific user."""
        with patch.object(api, '_tokens_dir', tmp_path):
            user_id = "test_user"
            
            # Save tokens
            api._save_tokens(user_id, {"access_token": "test_token"})
            assert api._load_tokens(user_id) is not None
            
            # Delete tokens
            api._delete_tokens(user_id)
            assert api._load_tokens(user_id) is None

    def test_get_token_path_sanitizes_user_id(self, tmp_path):
        """User IDs with special characters should be sanitized."""
        with patch.object(api, '_tokens_dir', tmp_path):
            # User ID with special characters
            user_id = "user@email.com/with/slashes"
            
            path = api._get_token_path(user_id)
            
            # Should not contain special characters
            assert "/" not in path.name
            assert "@" not in path.name
            assert ".com" not in path.name


class TestSessionManagement:
    """Test session cookie management for user authentication."""

    def test_session_created_on_oauth_success(self):
        """Session should be created when OAuth succeeds."""
        state = secrets.token_urlsafe(32)
        api._oauth_states[state] = time.time()
        
        with patch.object(api._oauth_http, 'post') as mock_post, \
             patch.object(api._oauth_http, 'get') as mock_get, \
             patch.object(api, '_cfg') as mock_cfg:
            
            mock_cfg.spotify.client_id = "test_id"
            mock_cfg.spotify.client_secret = "test_secret"
            mock_cfg.spotify.redirect_uri = "http://localhost:8000/auth/callback"
            
            # Mock token exchange
            mock_token_resp = Mock()
            mock_token_resp.status_code = 200
            mock_token_resp.json.return_value = {
                "access_token": "test_access",
                "refresh_token": "test_refresh",
                "expires_in": 3600,
            }
            
            # Mock /me endpoint
            mock_me_resp = Mock()
            mock_me_resp.is_success = True
            mock_me_resp.json.return_value = {"id": "test_user_123"}
            
            mock_post.return_value = mock_token_resp
            mock_get.return_value = mock_me_resp
            
            # Call callback via HTTP to exercise full FastAPI path
            client = TestClient(app)
            response = client.get(f"/auth/callback?code=test_code&state={state}")
            
            # Should have session cookie
            assert "simrai_session" in response.headers.get("set-cookie", "")
            
            # Session should map to user
            session_id = None
            for sid, uid in api._sessions.items():
                if uid == "test_user_123":
                    session_id = sid
                    break
            
            assert session_id is not None
            assert api._sessions[session_id] == "test_user_123"

    def test_get_session_user_id_with_valid_session(self):
        """Should return user_id for valid session."""
        session_id = "test_session_123"
        user_id = "test_user_456"
        api._sessions[session_id] = user_id
        
        # Mock request with session cookie
        mock_request = Mock()
        mock_request.cookies = {"simrai_session": session_id}
        
        result = api._get_session_user_id(mock_request)
        assert result == user_id

    def test_get_session_user_id_with_invalid_session(self):
        """Should raise HTTPException for invalid session."""
        mock_request = Mock()
        mock_request.cookies = {"simrai_session": "invalid_session"}
        
        with pytest.raises(api.HTTPException) as exc_info:
            api._get_session_user_id(mock_request)
        
        assert exc_info.value.status_code == 401
        assert "No active session" in exc_info.value.detail

    def test_get_session_user_id_with_no_cookie(self):
        """Should raise HTTPException when no session cookie."""
        mock_request = Mock()
        mock_request.cookies = {}
        
        with pytest.raises(api.HTTPException) as exc_info:
            api._get_session_user_id(mock_request)
        
        assert exc_info.value.status_code == 401

    def test_unlink_clears_session_and_tokens(self, tmp_path):
        """Unlinking should clear session and delete tokens."""
        with patch.object(api, '_tokens_dir', tmp_path):
            session_id = "test_session"
            user_id = "test_user"
            
            # Set up session and tokens
            api._sessions[session_id] = user_id
            api._save_tokens(user_id, {"access_token": "test"})
            
            # Mock request and response
            mock_request = Mock()
            mock_request.cookies = {"simrai_session": session_id}
            mock_response = Mock()
            
            # Call unlink
            result = api.api_unlink_spotify(mock_request, mock_response)
            
            # Session should be removed
            assert session_id not in api._sessions
            
            # Tokens should be deleted
            assert api._load_tokens(user_id) is None
            
            # Cookie should be deleted
            mock_response.delete_cookie.assert_called_once_with("simrai_session")


class TestConcurrentUserScenario:
    """Integration tests for concurrent user scenarios."""

    def test_two_users_connect_simultaneously(self, tmp_path):
        """Two users connecting at the same time should not conflict."""
        with patch.object(api, '_tokens_dir', tmp_path), \
             patch.object(api, '_cfg') as mock_cfg:
            
            mock_cfg.spotify.client_id = "test_id"
            mock_cfg.spotify.redirect_uri = "http://localhost:8000/auth/callback"
            
            # User A starts OAuth
            response_a = api.auth_login()
            state_a = list(api._oauth_states.keys())[0]
            
            # User B starts OAuth (before A completes)
            response_b = api.auth_login()
            state_b = [s for s in api._oauth_states.keys() if s != state_a][0]
            
            # Both states should be valid
            assert state_a in api._oauth_states
            assert state_b in api._oauth_states
            assert state_a != state_b

    def test_two_users_have_separate_tokens(self, tmp_path):
        """Two users should have completely separate token storage."""
        with patch.object(api, '_tokens_dir', tmp_path):
            user_a = "alice"
            user_b = "bob"
            
            # Both users save tokens
            api._save_tokens(user_a, {
                "access_token": "alice_token",
                "user_id": user_a
            })
            api._save_tokens(user_b, {
                "access_token": "bob_token",
                "user_id": user_b
            })
            
            # Verify isolation
            tokens_a = api._load_tokens(user_a)
            tokens_b = api._load_tokens(user_b)
            
            assert tokens_a["access_token"] == "alice_token"
            assert tokens_b["access_token"] == "bob_token"
            
            # Deleting one shouldn't affect the other
            api._delete_tokens(user_a)
            assert api._load_tokens(user_a) is None
            assert api._load_tokens(user_b) is not None


class TestTokenRefresh:
    """Test token refresh with per-user storage."""

    def test_token_refresh_updates_correct_user(self, tmp_path):
        """Token refresh should only update the specific user's tokens."""
        with patch.object(api, '_tokens_dir', tmp_path), \
             patch.object(api._oauth_http, 'post') as mock_post, \
             patch.object(api, '_cfg') as mock_cfg:
            
            mock_cfg.spotify.client_id = "test_id"
            mock_cfg.spotify.client_secret = "test_secret"
            
            user_id = "test_user"
            
            # Save expired tokens
            api._save_tokens(user_id, {
                "access_token": "old_token",
                "refresh_token": "refresh_token",
                "expires_at": time.time() - 100,  # Expired
            })
            
            # Mock refresh response
            mock_resp = Mock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = {
                "access_token": "new_token",
                "expires_in": 3600,
            }
            mock_post.return_value = mock_resp
            
            # Get token (should trigger refresh)
            new_token = api._get_user_access_token(user_id)
            
            assert new_token == "new_token"
            
            # Verify updated tokens
            tokens = api._load_tokens(user_id)
            assert tokens["access_token"] == "new_token"
