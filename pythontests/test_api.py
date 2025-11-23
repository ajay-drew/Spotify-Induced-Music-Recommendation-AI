from __future__ import annotations

import json
import time
from pathlib import Path
from typing import List
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from simrai.api import app, _get_user_access_token, _save_tokens, _tokens_path
from simrai.mood import MoodVector
from simrai.pipeline import QueueResult, QueueTrack


def _fake_generate_queue(
    mood_text: str,
    *,
    length: int = 12,
    intense: bool = False,
    soft: bool = False,
) -> QueueResult:  # noqa: ARG001
    tracks: List[QueueTrack] = [
        QueueTrack(
            name="Test Track",
            artists="Test Artist",
            uri="spotify:track:dummy",
            valence=0.7,
            energy=0.6,
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
    # Disable AI
    monkeypatch.setattr("simrai.pipeline.is_ai_available", lambda: False)

    # Use fake generate_queue that simulates rule-based behavior
    monkeypatch.setattr("simrai.api.generate_queue", _fake_generate_queue, raising=True)

    client = TestClient(app)
    resp = client.post("/queue", json={"mood": "test mood", "length": 10})

    assert resp.status_code == 200
    data = resp.json()
    assert data["mood"] == "test mood"
    assert len(data["tracks"]) > 0



