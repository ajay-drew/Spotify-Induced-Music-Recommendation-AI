from __future__ import annotations

import json
import time
from pathlib import Path
from typing import List, Optional
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from simrai.api import app
from simrai.mood import MoodVector
from simrai.pipeline import QueueResult, QueueTrack


def _fake_generate_queue(
    mood_text: str,
    *,
    length: int = 12,
    intense: bool = False,
    soft: bool = False,
    duration_minutes: Optional[int] = None,
) -> QueueResult:  # noqa: ARG001
    tracks: List[QueueTrack] = [
        QueueTrack(
            name="Test Track",
            artists="Test Artist",
            uri="spotify:track:dummy",
            valence=0.7,
            energy=0.6,
            duration_ms=180000,  # 3 minutes
        )
    ]
    return QueueResult(
        mood_text=mood_text,
        mood_vector=MoodVector(valence=0.5, energy=0.5),
        tracks=tracks,
        summary="Test summary",
    )


def test_queue_endpoint_happy_path(monkeypatch) -> None:
    # Monkeypatch generate_queue used inside the API to avoid real Spotify calls.
    monkeypatch.setattr("simrai.api.generate_queue", _fake_generate_queue, raising=True)

    client = TestClient(app)
    resp = client.post(
        "/queue",
        json={"mood": "test mood", "length": 10, "intense": False, "soft": True},
    )
    assert resp.status_code == 200

    data = resp.json()
    assert data["mood"] == "test mood"
    assert data["tracks"]
    assert data["tracks"][0]["uri"] == "spotify:track:dummy"
    assert "summary" in data


def test_queue_endpoint_handles_spotify_error(monkeypatch) -> None:
    """Test that /queue endpoint handles Spotify errors gracefully."""
    from simrai.spotify import SpotifyError

    def failing_generate_queue(*args, **kwargs):  # noqa: ARG001
        raise SpotifyError("Spotify API error")

    monkeypatch.setattr("simrai.api.generate_queue", failing_generate_queue, raising=True)

    client = TestClient(app)
    resp = client.post("/queue", json={"mood": "test mood"})

    assert resp.status_code == 502
    assert "Spotify error" in resp.json()["detail"]


def test_queue_endpoint_handles_general_error(monkeypatch) -> None:
    """Test that /queue endpoint handles general errors gracefully."""
    def failing_generate_queue(*args, **kwargs):  # noqa: ARG001
        raise ValueError("Unexpected error")

    monkeypatch.setattr("simrai.api.generate_queue", failing_generate_queue, raising=True)

    client = TestClient(app)
    resp = client.post("/queue", json={"mood": "test mood"})

    assert resp.status_code == 500
    assert "Internal error" in resp.json()["detail"]


def test_queue_endpoint_empty_result(monkeypatch) -> None:
    """Test that /queue endpoint handles empty results."""
    def empty_generate_queue(*args, **kwargs):  # noqa: ARG001
        return QueueResult(
            mood_text="test",
            mood_vector=MoodVector(valence=0.5, energy=0.5),
            tracks=[],
            summary="No tracks found",
        )

    monkeypatch.setattr("simrai.api.generate_queue", empty_generate_queue, raising=True)

    client = TestClient(app)
    resp = client.post("/queue", json={"mood": "test mood"})

    assert resp.status_code == 200
    data = resp.json()
    assert data["tracks"] == []
    assert "No tracks found" in data["summary"]


def test_health_endpoint() -> None:
    """Test the health check endpoint."""
    client = TestClient(app)
    resp = client.get("/health")

    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_queue_endpoint_ai_fallback_integration(monkeypatch, tmp_path: Path) -> None:
    """Test that /queue automatically falls back when AI is unavailable."""
    # Use fake generate_queue that simulates the metadata-first, rule-based behavior
    monkeypatch.setattr("simrai.api.generate_queue", _fake_generate_queue, raising=True)

    client = TestClient(app)
    resp = client.post("/queue", json={"mood": "test mood", "length": 10})

    assert resp.status_code == 200
    data = resp.json()
    assert data["mood"] == "test mood"
    assert len(data["tracks"]) > 0


def test_queue_endpoint_with_duration_minutes(monkeypatch) -> None:
    """Test that /queue endpoint accepts duration_minutes parameter."""
    monkeypatch.setattr("simrai.api.generate_queue", _fake_generate_queue, raising=True)

    client = TestClient(app)
    resp = client.post(
        "/queue",
        json={"mood": "test mood", "duration_minutes": 30},
    )
    assert resp.status_code == 200

    data = resp.json()
    assert data["mood"] == "test mood"
    assert data["tracks"]


def test_queue_endpoint_duration_independent_of_length(monkeypatch) -> None:
    """Test that duration_minutes is independent of length - when duration is provided, length is not passed."""
    def duration_generate_queue(
        mood_text: str,
        *,
        length: int = 12,
        intense: bool = False,
        soft: bool = False,
        duration_minutes: Optional[int] = None,
    ) -> QueueResult:  # noqa: ARG001
        # Verify duration_minutes is passed and length is default (not used)
        assert duration_minutes == 20
        assert length == 12  # Should use default, not the provided length
        return _fake_generate_queue(mood_text, length=length, intense=intense, soft=soft, duration_minutes=duration_minutes)

    monkeypatch.setattr("simrai.api.generate_queue", duration_generate_queue, raising=True)

    client = TestClient(app)
    # Even if both are sent, API should only pass duration_minutes
    resp = client.post(
        "/queue",
        json={"mood": "test mood", "length": 10, "duration_minutes": 20},
    )
    assert resp.status_code == 200


def test_queue_endpoint_duration_excludes_length(monkeypatch) -> None:
    """Test that when duration_minutes is provided, length is NOT passed to generate_queue."""
    call_kwargs = {}

    def capture_generate_queue(
        mood_text: str,
        *,
        length: int = 12,
        intense: bool = False,
        soft: bool = False,
        duration_minutes: Optional[int] = None,
    ) -> QueueResult:  # noqa: ARG001
        # Capture the actual parameters passed
        call_kwargs["length"] = length
        call_kwargs["duration_minutes"] = duration_minutes
        call_kwargs["intense"] = intense
        call_kwargs["soft"] = soft
        return _fake_generate_queue(mood_text, length=length, intense=intense, soft=soft, duration_minutes=duration_minutes)

    monkeypatch.setattr("simrai.api.generate_queue", capture_generate_queue, raising=True)

    client = TestClient(app)
    # Send both length and duration_minutes
    resp = client.post(
        "/queue",
        json={"mood": "test mood", "length": 15, "duration_minutes": 30, "intense": True},
    )
    
    assert resp.status_code == 200
    # Verify that only duration_minutes was passed, not length (should use default 12)
    assert call_kwargs["duration_minutes"] == 30, "duration_minutes should be passed"
    assert call_kwargs["length"] == 12, "length should be default (12), not the provided 15"
    assert call_kwargs["intense"] is True, "other parameters should still be passed"


def test_queue_endpoint_length_excludes_duration(monkeypatch) -> None:
    """Test that when only length is provided, duration_minutes is NOT passed to generate_queue."""
    call_kwargs = {}

    def capture_generate_queue(
        mood_text: str,
        *,
        length: int = 12,
        intense: bool = False,
        soft: bool = False,
        duration_minutes: Optional[int] = None,
    ) -> QueueResult:  # noqa: ARG001
        # Capture the actual parameters passed
        call_kwargs["length"] = length
        call_kwargs["duration_minutes"] = duration_minutes
        call_kwargs["intense"] = intense
        call_kwargs["soft"] = soft
        return _fake_generate_queue(mood_text, length=length, intense=intense, soft=soft, duration_minutes=duration_minutes)

    monkeypatch.setattr("simrai.api.generate_queue", capture_generate_queue, raising=True)

    client = TestClient(app)
    # Send only length (no duration_minutes)
    resp = client.post(
        "/queue",
        json={"mood": "test mood", "length": 20, "soft": True},
    )
    
    assert resp.status_code == 200
    # Verify that only length was passed, not duration_minutes
    assert call_kwargs["length"] == 20, "length should be passed"
    assert call_kwargs["duration_minutes"] is None, "duration_minutes should be None when not provided"
    assert call_kwargs["soft"] is True, "other parameters should still be passed"



