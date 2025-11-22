"""
Minimal end-to-end pipeline for SIMRAI (v0).

Steps:
1) Interpret mood text into a MoodVector and search terms.
2) Use SpotifyService to search for candidate tracks.
3) Fetch audio features for candidates.
4) Score each track against the mood vector.
5) Build a simple ordered queue (gentle rise in energy where possible).
"""

from __future__ import annotations

from dataclasses import dataclass
from math import sqrt
from typing import List, Optional

from .mood import MoodInterpretation, MoodVector, interpret_mood
from .spotify import SpotifyService, SpotifyAPIError


@dataclass
class QueueTrack:
    name: str
    artists: str
    uri: str
    valence: float
    energy: float
    popularity: Optional[int] = None
    year: Optional[int] = None


@dataclass
class QueueResult:
    mood_text: str
    mood_vector: MoodVector
    tracks: List[QueueTrack]
    summary: str


def _score_track(vec: MoodVector, features: dict) -> float:
    """
    Compute a simple distance-based score: lower distance => higher score.
    """
    v = features.get("valence")
    e = features.get("energy")
    if v is None or e is None:
        return -1.0
    dv = v - vec.valence
    de = e - vec.energy
    dist = sqrt(dv * dv + de * de)
    # Convert distance in [0, sqrt(2)] to score ~ [0, 1]
    max_dist = sqrt(2.0)
    return 1.0 - (dist / max_dist)


def _metadata_valence_energy(
    vec: MoodVector,
    interpretation: MoodInterpretation,
    popularity: Optional[int],
    year: Optional[int],
    text: str,
) -> tuple[float, float]:
    """
    Derive a synthetic (valence, energy) estimate from metadata only.

    This is a heuristic used when Spotify audio features are unavailable.
    """
    # Normalize popularity to [0, 1].
    pop_norm = 0.0
    if popularity is not None:
        pop_norm = max(0.0, min(1.0, popularity / 100.0))

    # Normalize year very roughly between 1970 and 2025.
    year_norm = 0.5
    if year is not None:
        y = max(1970, min(2025, year))
        year_norm = (y - 1970) / (2025 - 1970)

    # Start near the mood vector.
    base_v = vec.valence
    base_e = vec.energy

    # Use popularity and year as signals:
    # - newer & more popular tracks skew higher energy and valence.
    v = base_v + 0.20 * (year_norm - 0.5) + 0.15 * (pop_norm - 0.5)
    e = base_e + 0.40 * (pop_norm - 0.5) + 0.25 * (year_norm - 0.5)

    # Text-based heuristics from track/album names.
    lowered = text.lower()
    high_energy_tokens = (
        "remix",
        "rmx",
        "club",
        "live",
        "edit",
        "mix",
        "bass",
        "trap",
        "drum",
        "dubstep",
    )
    low_energy_tokens = (
        "acoustic",
        "piano",
        "ambient",
        "lofi",
        "lo-fi",
        "unplugged",
        "ballad",
        "instrumental",
    )
    if any(tok in lowered for tok in high_energy_tokens):
        e += 0.15
        v += 0.05
    if any(tok in lowered for tok in low_energy_tokens):
        e -= 0.15
        v -= 0.05

    # Apply user preferences.
    if interpretation.prefer_obscure:
        e -= 0.05
    if interpretation.prefer_popular:
        e += 0.05
    if interpretation.prefer_classics:
        v -= 0.05
    if interpretation.prefer_recent:
        v += 0.05

    # Clamp to [0, 1].
    v = max(0.0, min(1.0, v))
    e = max(0.0, min(1.0, e))
    return v, e


def generate_queue(
    mood_text: str,
    *,
    length: int = 12,
    intense: bool = False,
    soft: bool = False,
) -> QueueResult:
    """
    Generate a simple ordered queue for a mood using the v0 pipeline.
    """
    interpretation: MoodInterpretation = interpret_mood(mood_text, intense=intense, soft=soft)
    vector = interpretation.vector

    service = SpotifyService()
    audio_features_available = True
    try:
        # Phase 1/2: single combined search term string for now.
        query = " ".join(interpretation.search_terms)
        candidates = service.search_tracks(query, limit=max(length * 3, 40))

        if not candidates:
            return QueueResult(
                mood_text=mood_text,
                mood_vector=vector,
                tracks=[],
                summary="No tracks found for this mood.",
            )

        ids = [t.get("id") for t in candidates if t.get("id")]
        try:
            features_by_id = service.get_audio_features(ids)
        except SpotifyAPIError:
            # If Spotify refuses access to audio-features (e.g., 403),
            # fall back to using search results only.
            audio_features_available = False
            features_by_id = {}
    finally:
        service.close()

    scored_tracks: List[QueueTrack] = []
    for t in candidates:
        tid = t.get("id")
        if not tid or tid not in features_by_id:
            continue
        features = features_by_id[tid]
        score = _score_track(vector, features)
        if score < 0:
            continue

        name = t.get("name", "<unknown>")
        artists = ", ".join(a.get("name", "") for a in t.get("artists", []) or [])
        uri = t.get("uri") or f"spotify:track:{tid}"
        valence = float(features.get("valence", 0.0))
        energy = float(features.get("energy", 0.0))

        scored_tracks.append(
            QueueTrack(
                name=name,
                artists=artists,
                uri=uri,
                valence=valence,
                energy=energy,
            )
        )

    if not scored_tracks:
        if not audio_features_available:
            # Fallback: use top-N search results without psychoacoustic scoring,
            # but still apply some metadata-aware ordering (popularity / year).
            fallback: List[QueueTrack] = []
            for t in candidates:
                tid = t.get("id")
                name = t.get("name", "<unknown>")
                artists = ", ".join(a.get("name", "") for a in t.get("artists", []) or [])
                uri = t.get("uri") or (f"spotify:track:{tid}" if tid else "<unknown>")
                popularity = t.get("popularity")
                # Parse year from album.release_date if available.
                album = t.get("album") or {}
                year_str = album.get("release_date") or ""
                year: Optional[int] = None
                if isinstance(year_str, str) and len(year_str) >= 4 and year_str[:4].isdigit():
                    year = int(year_str[:4])

                # Use track + album name for text-based heuristics.
                text = f"{name} {album.get('name', '')}"
                valence, energy = _metadata_valence_energy(vector, interpretation, popularity, year, text)

                fallback.append(
                    QueueTrack(
                        name=name,
                        artists=artists,
                        uri=uri,
                        valence=valence,
                        energy=energy,
                        popularity=popularity,
                        year=year,
                    )
                )

            # Simple metadata-based ranking:
            # - If mood prefers classics, favor older tracks; if recent, favor newer.
            # - Otherwise, sort primarily by popularity (high to low).
            def meta_score(track: QueueTrack) -> float:
                pop = track.popularity if track.popularity is not None else 0
                year = track.year if track.year is not None else 0

                score = float(pop)
                if interpretation.prefer_recent:
                    score += (year - 2000) * 0.2  # reward newer tracks modestly
                if interpretation.prefer_classics:
                    score -= (year - 2000) * 0.2  # reward older tracks modestly
                if interpretation.prefer_obscure:
                    score -= pop * 0.5  # penalize mainstream a bit
                if interpretation.prefer_popular:
                    score += pop * 0.5  # emphasize hits
                return score

            fallback.sort(key=meta_score, reverse=True)
            selected_fb = fallback[: max(1, length)]

            summary = (
                "Audio features endpoint is unavailable (e.g., Spotify 403). "
                "This queue is based on metadata-driven ranking (popularity and year) only."
            )
            return QueueResult(
                mood_text=mood_text,
                mood_vector=vector,
                tracks=selected_fb,
                summary=summary,
            )
        else:
            return QueueResult(
                mood_text=mood_text,
                mood_vector=vector,
                tracks=[],
                summary="No suitable tracks with audio features found for this mood.",
            )

    # Sort by score (desc), then apply a gentle energy-based ordering tweak:
    # first take the best N by score, then sort those by energy to create a simple arc.
    scored_tracks.sort(
        key=lambda t: _score_track(
            vector,
            {"valence": t.valence, "energy": t.energy},
        ),
        reverse=True,
    )
    selected = scored_tracks[: max(1, length)]
    selected.sort(key=lambda t: t.energy)

    # Simple summary string.
    if selected:
        start_v = selected[0].valence
        end_v = selected[-1].valence
        summary = (
            f"This queue starts at valence {start_v:.2f} and "
            f"moves toward {end_v:.2f} (energy rises gently)."
        )
    else:
        summary = "Generated an empty queue."

    return QueueResult(
        mood_text=mood_text,
        mood_vector=vector,
        tracks=selected,
        summary=summary,
    )


__all__ = ["QueueTrack", "QueueResult", "generate_queue"]


