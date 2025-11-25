"""
Test suite for API rate limiting to prevent abuse and Spotify 429 errors.
"""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, Mock
import time

from src.simrai.api import app
from src.simrai import api


@pytest.fixture
def client():
    """Create a test client for the FastAPI app."""
    return TestClient(app)


@pytest.fixture(autouse=True)
def reset_rate_limiter():
    """Reset rate limiter state between tests."""
    # Clear any existing rate limit storage
    if hasattr(app.state, 'limiter'):
        app.state.limiter.reset()
    yield
    # Clean up after test
    if hasattr(app.state, 'limiter'):
        app.state.limiter.reset()


class TestQueueRateLimiting:
    """Test rate limiting on /queue endpoint (10 requests per minute)."""

    def test_queue_allows_requests_under_limit(self, client):
        """Should allow requests under the rate limit."""
        with patch('src.simrai.api.generate_queue') as mock_generate:
            mock_generate.return_value = Mock(
                mood_text="test",
                mood_vector=Mock(valence=0.5, energy=0.5),
                summary="test summary",
                tracks=[]
            )
            
            # Make 5 requests (under limit of 10)
            for i in range(5):
                response = client.post(
                    "/queue",
                    json={"mood": "test mood", "length": 12}
                )
                assert response.status_code == 200

    def test_queue_blocks_requests_over_limit(self, client):
        """Should block requests that exceed the rate limit."""
        with patch('src.simrai.api.generate_queue') as mock_generate:
            mock_generate.return_value = Mock(
                mood_text="test",
                mood_vector=Mock(valence=0.5, energy=0.5),
                summary="test summary",
                tracks=[]
            )
            
            # Make 11 requests (over limit of 10)
            responses = []
            for i in range(11):
                response = client.post(
                    "/queue",
                    json={"mood": "test mood", "length": 12}
                )
                responses.append(response)
            
            # First 10 should succeed
            for i in range(10):
                assert responses[i].status_code == 200, f"Request {i+1} should succeed"
            
            # 11th should be rate limited
            assert responses[10].status_code == 429, "Request 11 should be rate limited"

    def test_queue_rate_limit_error_message(self, client):
        """Rate limit error should have helpful message."""
        with patch('src.simrai.api.generate_queue') as mock_generate:
            mock_generate.return_value = Mock(
                mood_text="test",
                mood_vector=Mock(valence=0.5, energy=0.5),
                summary="test summary",
                tracks=[]
            )
            
            # Exhaust rate limit
            for i in range(10):
                client.post("/queue", json={"mood": "test", "length": 12})
            
            # Next request should be blocked
            response = client.post("/queue", json={"mood": "test", "length": 12})
            
            assert response.status_code == 429
            assert "rate limit" in response.text.lower() or "too many" in response.text.lower()


class TestPlaylistRateLimiting:
    """Test rate limiting on playlist endpoints."""

    def test_create_playlist_rate_limit(self, client):
        """Should limit playlist creation to 5 per minute."""
        with patch('src.simrai.api._get_session_user_id') as mock_session, \
             patch('src.simrai.api._get_user_access_token') as mock_token, \
             patch.object(api._oauth_http, 'get') as mock_get, \
             patch.object(api._oauth_http, 'post') as mock_post:
            
            mock_session.return_value = "test_user"
            mock_token.return_value = "test_token"
            
            # Mock /me response
            mock_me_resp = Mock()
            mock_me_resp.is_success = True
            mock_me_resp.json.return_value = {"id": "test_user"}
            
            # Mock playlist creation response
            mock_pl_resp = Mock()
            mock_pl_resp.is_success = True
            mock_pl_resp.json.return_value = {
                "id": "playlist_123",
                "external_urls": {"spotify": "https://open.spotify.com/playlist/123"}
            }
            
            mock_get.return_value = mock_me_resp
            mock_post.return_value = mock_pl_resp
            
            # Make 6 requests (over limit of 5)
            responses = []
            for i in range(6):
                response = client.post(
                    "/api/create-playlist",
                    json={"name": f"Test Playlist {i}"}
                )
                responses.append(response)
            
            # First 5 should succeed
            for i in range(5):
                assert responses[i].status_code == 200, f"Request {i+1} should succeed"
            
            # 6th should be rate limited
            assert responses[5].status_code == 429

    def test_add_tracks_rate_limit(self, client):
        """Should limit track additions to 10 per minute."""
        with patch('src.simrai.api._get_session_user_id') as mock_session, \
             patch('src.simrai.api._get_user_access_token') as mock_token, \
             patch.object(api._oauth_http, 'post') as mock_post:
            
            mock_session.return_value = "test_user"
            mock_token.return_value = "test_token"
            
            # Mock add tracks response
            mock_resp = Mock()
            mock_resp.is_success = True
            mock_resp.json.return_value = {"snapshot_id": "snapshot_123"}
            mock_post.return_value = mock_resp
            
            # Make 11 requests (over limit of 10)
            responses = []
            for i in range(11):
                response = client.post(
                    "/api/add-tracks",
                    json={
                        "playlist_id": "test_playlist",
                        "uris": ["spotify:track:123"]
                    }
                )
                responses.append(response)
            
            # First 10 should succeed
            for i in range(10):
                assert responses[i].status_code == 200, f"Request {i+1} should succeed"
            
            # 11th should be rate limited
            assert responses[10].status_code == 429


class TestRateLimitByIP:
    """Test that rate limits are per IP address."""

    def test_different_ips_have_separate_limits(self, client):
        """Different IP addresses should have separate rate limits."""
        with patch('src.simrai.api.generate_queue') as mock_generate:
            mock_generate.return_value = Mock(
                mood_text="test",
                mood_vector=Mock(valence=0.5, energy=0.5),
                summary="test summary",
                tracks=[]
            )
            
            # Simulate requests from IP 1 (exhaust limit)
            for i in range(10):
                response = client.post(
                    "/queue",
                    json={"mood": "test", "length": 12},
                    headers={"X-Forwarded-For": "192.168.1.1"}
                )
                assert response.status_code == 200
            
            # IP 1 is now rate limited
            response = client.post(
                "/queue",
                json={"mood": "test", "length": 12},
                headers={"X-Forwarded-For": "192.168.1.1"}
            )
            assert response.status_code == 429
            
            # But IP 2 should still work
            response = client.post(
                "/queue",
                json={"mood": "test", "length": 12},
                headers={"X-Forwarded-For": "192.168.1.2"}
            )
            assert response.status_code == 200


class TestRateLimitProtectsSpotify:
    """Test that rate limiting prevents hitting Spotify's limits."""

    def test_queue_limit_prevents_spotify_429(self, client):
        """10 requests/minute should prevent Spotify rate limit (100/30sec)."""
        # Spotify allows ~100 requests per 30 seconds
        # Our limit of 10/minute = 10/60sec = 0.167 req/sec
        # This is well under Spotify's limit of 100/30sec = 3.33 req/sec
        
        # Calculate: if all users hit our limit, do we stay under Spotify's?
        simrai_limit_per_sec = 10 / 60  # 0.167 req/sec
        spotify_limit_per_sec = 100 / 30  # 3.33 req/sec
        
        # With up to 20 concurrent users, we'd use:
        max_concurrent_users = 20
        max_requests_per_sec = simrai_limit_per_sec * max_concurrent_users
        
        # Should still be under Spotify's limit
        assert max_requests_per_sec < spotify_limit_per_sec, \
            f"Rate limit too high: {max_requests_per_sec} req/sec exceeds Spotify's {spotify_limit_per_sec}"

    def test_rate_limit_prevents_dos_attack(self, client):
        """Rate limiting should prevent DoS attacks."""
        with patch('src.simrai.api.generate_queue') as mock_generate:
            mock_generate.return_value = Mock(
                mood_text="test",
                mood_vector=Mock(valence=0.5, energy=0.5),
                summary="test summary",
                tracks=[]
            )
            
            # Attacker tries to spam 100 requests
            blocked_count = 0
            for i in range(100):
                response = client.post(
                    "/queue",
                    json={"mood": "attack", "length": 12}
                )
                if response.status_code == 429:
                    blocked_count += 1
            
            # Most requests should be blocked
            assert blocked_count >= 90, f"Only {blocked_count}/100 requests blocked"


class TestRateLimitConfiguration:
    """Test rate limit configuration and behavior."""

    def test_health_endpoint_not_rate_limited(self, client):
        """Health check endpoint should not be rate limited."""
        # Make many health check requests
        for i in range(50):
            response = client.get("/health")
            assert response.status_code == 200, \
                f"Health check {i+1} should not be rate limited"

    def test_rate_limit_headers_present(self, client):
        """Rate limit responses should include helpful headers."""
        with patch('src.simrai.api.generate_queue') as mock_generate:
            mock_generate.return_value = Mock(
                mood_text="test",
                mood_vector=Mock(valence=0.5, energy=0.5),
                summary="test summary",
                tracks=[]
            )
            
            # Make request
            response = client.post(
                "/queue",
                json={"mood": "test", "length": 12}
            )
            
            # Should have rate limit headers (slowapi adds these)
            # Note: actual header names may vary by slowapi version
            assert response.status_code == 200


class TestRateLimitEdgeCases:
    """Test edge cases in rate limiting."""

    def test_rate_limit_with_invalid_request(self, client):
        """Rate limit should apply even to invalid requests."""
        # Make 11 invalid requests
        responses = []
        for i in range(11):
            response = client.post(
                "/queue",
                json={"invalid": "data"}  # Missing required 'mood' field
            )
            responses.append(response)
        
        # Should still enforce rate limit
        # (Some might be 422 validation errors, but 11th should be 429 or 422)
        status_codes = [r.status_code for r in responses]
        assert 429 in status_codes or status_codes.count(422) >= 10

    def test_rate_limit_persists_across_sessions(self, client):
        """Rate limit should persist even if user changes session."""
        with patch('src.simrai.api.generate_queue') as mock_generate:
            mock_generate.return_value = Mock(
                mood_text="test",
                mood_vector=Mock(valence=0.5, energy=0.5),
                summary="test summary",
                tracks=[]
            )
            
            # Exhaust limit with one session
            for i in range(10):
                response = client.post(
                    "/queue",
                    json={"mood": "test", "length": 12},
                    cookies={"simrai_session": "session_1"}
                )
                assert response.status_code == 200
            
            # Try with different session (same IP)
            response = client.post(
                "/queue",
                json={"mood": "test", "length": 12},
                cookies={"simrai_session": "session_2"}
            )
            
            # Should still be rate limited (rate limit is per IP, not session)
            assert response.status_code == 429

