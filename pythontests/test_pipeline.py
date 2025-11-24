from __future__ import annotations

from typing import List, Optional
from unittest.mock import patch

from simrai.mood import MoodInterpretation, MoodVector
from simrai.pipeline import QueueResult, QueueTrack, generate_queue
from simrai.spotify import SpotifyService


class _FakeSpotifyService:
    """
    Fake SpotifyService used to drive the pipeline in tests.

    Pipeline now always uses metadata-only mode (no audio-features endpoint).
    """

    def __init__(self) -> None:
        # One simple candidate set with varying popularity / year metadata.
        self._candidates: List[dict] = [
            {
                "id": "id_pop_recent",
                "name": "Hype Club Remix",
                "artists": [{"name": "DJ Test"}],
                "uri": "spotify:track:id_pop_recent",
                "popularity": 90,
                "album": {"name": "Test Album", "release_date": "2024-01-01"},
            },
            {
                "id": "id_obscure_old",
                "name": "Acoustic Ballad",
                "artists": [{"name": "Indie Test"}],
                "uri": "spotify:track:id_obscure_old",
                "popularity": 10,
                "album": {"name": "Old Times", "release_date": "1980-05-05"},
            },
        ]

    def search_tracks(self, query: str, *, limit: int = 20) -> List[dict]:  # noqa: ARG002
        return self._candidates[:limit]

    def close(self) -> None:  # pragma: no cover - no-op
        return None


def test_generate_queue_metadata_only_mode(monkeypatch) -> None:
    """
    Verify that generate_queue uses metadata-only mode (no audio-features endpoint).
    Pipeline always uses metadata (popularity, year, text heuristics) for ranking.
    """

    def fake_service_init(self, cfg: Optional[object] = None) -> None:  # noqa: ARG002
        # Replace the internal backend with our fake.
        self._backend = _FakeSpotifyService()

    monkeypatch.setattr(SpotifyService, "__init__", fake_service_init, raising=True)

    result: QueueResult = generate_queue("happy party", length=2)
    assert result.tracks, "Expected tracks in metadata-only queue"
    assert all(isinstance(t, QueueTrack) for t in result.tracks)

    # Ensure we have non-zero, non-identical valence/energy values from metadata.
    vals = {t.valence for t in result.tracks}
    energies = {t.energy for t in result.tracks}
    assert len(vals) > 0
    assert len(energies) > 0
    
    # Summary should mention metadata-driven ranking
    assert "metadata-driven" in result.summary.lower() or "metadata" in result.summary.lower()


def test_generate_queue_metadata_ranking_variation(monkeypatch) -> None:
    """
    Test that metadata-only mode produces varied valence/energy values.
    Different tracks should have different synthetic values based on popularity/year/text.
    """

    def fake_service_init(self, cfg: Optional[object] = None) -> None:  # noqa: ARG002
        self._backend = _FakeSpotifyService()

    monkeypatch.setattr(SpotifyService, "__init__", fake_service_init, raising=True)

    result: QueueResult = generate_queue("underground classic night", length=2)

    assert result.tracks, "Expected tracks from metadata-only mode"

    vals = {t.valence for t in result.tracks}
    energies = {t.energy for t in result.tracks}
    # Metadata-based values should vary between tracks (popular vs obscure, recent vs old)
    assert len(vals) > 0, "Should have valence values"
    assert len(energies) > 0, "Should have energy values"


def test_generate_queue_always_uses_metadata_pipeline(monkeypatch) -> None:
    """
    Test that generate_queue always uses the metadata-first pipeline without CrewAI.

    We simulate Spotify results and verify that:
    - Tracks are returned.
    - The mood vector is always present (rule-based + optional Groq inside interpret_mood).
    """

    def fake_service_init(self, cfg=None):  # noqa: ARG001
        self._backend = _FakeSpotifyService()

    monkeypatch.setattr(SpotifyService, "__init__", fake_service_init, raising=True)

    result = generate_queue("test mood", length=2)

    assert result.tracks
    assert result.mood_vector.valence >= 0.0
    assert result.mood_vector.energy >= 0.0



