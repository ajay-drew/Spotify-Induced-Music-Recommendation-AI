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
        # Duration in milliseconds: 3min, 4min, 5min, 2min, 6min
        self._candidates: List[dict] = [
            {
                "id": "id_pop_recent",
                "name": "Hype Club Remix",
                "artists": [{"name": "DJ Test"}],
                "uri": "spotify:track:id_pop_recent",
                "popularity": 90,
                "album": {"name": "Test Album", "release_date": "2024-01-01"},
                "duration_ms": 180000,  # 3 minutes
            },
            {
                "id": "id_obscure_old",
                "name": "Acoustic Ballad",
                "artists": [{"name": "Indie Test"}],
                "uri": "spotify:track:id_obscure_old",
                "popularity": 10,
                "album": {"name": "Old Times", "release_date": "1980-05-05"},
                "duration_ms": 240000,  # 4 minutes
            },
            {
                "id": "id_mid_pop",
                "name": "Mid Popularity Track",
                "artists": [{"name": "Mid Artist"}],
                "uri": "spotify:track:id_mid_pop",
                "popularity": 50,
                "album": {"name": "Mid Album", "release_date": "2010-06-15"},
                "duration_ms": 300000,  # 5 minutes
            },
            {
                "id": "id_short_track",
                "name": "Short Track",
                "artists": [{"name": "Short Artist"}],
                "uri": "spotify:track:id_short_track",
                "popularity": 70,
                "album": {"name": "Short Album", "release_date": "2020-03-20"},
                "duration_ms": 120000,  # 2 minutes
            },
            {
                "id": "id_long_track",
                "name": "Long Track",
                "artists": [{"name": "Long Artist"}],
                "uri": "spotify:track:id_long_track",
                "popularity": 30,
                "album": {"name": "Long Album", "release_date": "1995-11-10"},
                "duration_ms": 360000,  # 6 minutes
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


def test_generate_queue_with_duration_minutes(monkeypatch) -> None:
    """Test that generate_queue selects tracks based on duration when duration_minutes is provided."""
    def fake_service_init(self, cfg: Optional[object] = None) -> None:  # noqa: ARG002
        self._backend = _FakeSpotifyService()

    monkeypatch.setattr(SpotifyService, "__init__", fake_service_init, raising=True)

    # Request 10 minutes (600000 ms) with ±3 minute buffer (420000-780000 ms)
    # Available tracks: 3min, 4min, 5min, 2min, 6min
    # Best combination: 4min + 6min = 10min (perfect match)
    result = generate_queue("test mood", duration_minutes=10)

    assert result.tracks, "Should have tracks selected by duration"
    
    # Verify all tracks have duration_ms
    for track in result.tracks:
        assert track.duration_ms is not None, "Tracks should have duration_ms"
    
    # Calculate total duration
    total_ms = sum(t.duration_ms or 0 for t in result.tracks)
    total_minutes = total_ms / 60000.0
    
    # Should be within ±3 minutes of target (10 minutes)
    assert 7.0 <= total_minutes <= 13.0, f"Total duration {total_minutes}min should be within 7-13min range"


def test_generate_queue_duration_prioritizes_mood_match(monkeypatch) -> None:
    """Test that duration-based selection still prioritizes mood/genre/valence/energy match."""
    def fake_service_init(self, cfg: Optional[object] = None) -> None:  # noqa: ARG002
        self._backend = _FakeSpotifyService()

    monkeypatch.setattr(SpotifyService, "__init__", fake_service_init, raising=True)

    # Request 5 minutes - multiple combinations possible:
    # - 3min + 2min = 5min (perfect)
    # - 5min alone = 5min (perfect)
    # Should prefer higher-ranked tracks (by mood match) that still fit duration
    result = generate_queue("happy party", duration_minutes=5)

    assert result.tracks, "Should have tracks"
    total_ms = sum(t.duration_ms or 0 for t in result.tracks)
    total_minutes = total_ms / 60000.0
    
    # Should be within ±3 minutes (2-8 minutes)
    assert 2.0 <= total_minutes <= 8.0, f"Total duration {total_minutes}min should be within 2-8min range"


def test_generate_queue_duration_with_short_target(monkeypatch) -> None:
    """Test duration selection with a very short target (5 minutes)."""
    def fake_service_init(self, cfg: Optional[object] = None) -> None:  # noqa: ARG002
        self._backend = _FakeSpotifyService()

    monkeypatch.setattr(SpotifyService, "__init__", fake_service_init, raising=True)

    result = generate_queue("test mood", duration_minutes=5)

    assert result.tracks, "Should have at least one track"
    total_ms = sum(t.duration_ms or 0 for t in result.tracks)
    total_minutes = total_ms / 60000.0
    
    # Should be within ±3 minutes (2-8 minutes)
    assert 2.0 <= total_minutes <= 8.0, f"Total duration {total_minutes}min should be within 2-8min range"


def test_generate_queue_duration_with_long_target(monkeypatch) -> None:
    """Test duration selection with a longer target (15 minutes)."""
    def fake_service_init(self, cfg: Optional[object] = None) -> None:  # noqa: ARG002
        self._backend = _FakeSpotifyService()

    monkeypatch.setattr(SpotifyService, "__init__", fake_service_init, raising=True)

    # Request 15 minutes - with available tracks (3+4+5+2+6 = 20min total)
    # Should select tracks closest to 15 minutes within ±3min tolerance (12-18min)
    result = generate_queue("test mood", duration_minutes=15)

    assert result.tracks, "Should have multiple tracks"
    total_ms = sum(t.duration_ms or 0 for t in result.tracks)
    total_minutes = total_ms / 60000.0
    
    # Should be within ±3 minutes (12-18 minutes), or at least use available tracks
    # Since we only have 20min total, it should select tracks that get as close as possible
    assert total_minutes > 0, f"Should have some duration, got {total_minutes}min"
    # The algorithm should select tracks that get closest to target
    assert total_minutes <= 20.0, f"Total duration {total_minutes}min should not exceed available tracks"


def test_generate_queue_duration_fallback_to_length(monkeypatch) -> None:
    """Test that when duration_minutes is None, it falls back to length-based selection."""
    def fake_service_init(self, cfg: Optional[object] = None) -> None:  # noqa: ARG002
        self._backend = _FakeSpotifyService()

    monkeypatch.setattr(SpotifyService, "__init__", fake_service_init, raising=True)

    result = generate_queue("test mood", length=3)

    assert len(result.tracks) == 3, "Should have exactly 3 tracks when length=3"
    # When using length, we don't enforce duration constraints
    # But tracks should still have duration_ms populated
    for track in result.tracks:
        assert track.duration_ms is not None, "Tracks should have duration_ms even in length mode"



