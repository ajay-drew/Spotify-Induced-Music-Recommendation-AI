"""
Minimal end-to-end pipeline for SIMRAI (v0).

Steps:
1) Interpret mood text into a MoodVector and search terms.
2) Use SpotifyService to search for candidate tracks.
3) Score tracks using metadata (popularity, year, text heuristics).
4) Build a simple ordered queue (gentle rise in energy where possible).

Note: This pipeline uses metadata-only mode (no audio-features endpoint).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import List, Optional

from .mood import MoodInterpretation, MoodVector, interpret_mood
from .spotify import SpotifyService

logger = logging.getLogger(__name__)


@dataclass
class QueueTrack:
    name: str
    artists: str
    uri: str
    valence: float
    energy: float
    popularity: Optional[int] = None
    year: Optional[int] = None
    duration_ms: Optional[int] = None


@dataclass
class QueueResult:
    mood_text: str
    mood_vector: MoodVector
    tracks: List[QueueTrack]
    summary: str


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
    duration_minutes: Optional[int] = None,
    intense: bool = False,
    soft: bool = False,
    ) -> QueueResult:
    """
    Generate a simple ordered queue for a mood using the v0 pipeline.

    This pipeline is **metadata-first** and **Groq-backed**:
    - `interpret_mood` always runs locally and optionally calls Groq (if configured)
      to refine the mood vector and search terms.
    - Queue generation itself is purely metadata-based (Spotify search + heuristics),
      with no CrewAI or audio-features endpoint.
    """
    logger.info(
        "Generating queue for mood: %r (length=%d, duration=%s, intense=%s, soft=%s)",
        mood_text,
        length,
        duration_minutes,
        intense,
        soft,
    )

    # Interpret mood (rule-based core with optional Groq refinement inside interpret_mood)
    logger.debug("Interpreting mood using rule-based + optional Groq refinement")
    interpretation: MoodInterpretation = interpret_mood(mood_text, intense=intense, soft=soft)
    vector = interpretation.vector
    logger.debug(f"Mood vector: valence={vector.valence:.2f}, energy={vector.energy:.2f}, search_terms={interpretation.search_terms}")

    service = SpotifyService()
    try:
        # Search for candidate tracks using mood interpretation
        query = " ".join(interpretation.search_terms)
        logger.info(f"Searching Spotify for: {query!r}")
        # When duration_minutes is provided, use a large search limit to ensure we have enough tracks
        # When only length is provided, use length-based limit
        if duration_minutes and duration_minutes > 0:
            search_limit = 100  # Large limit for duration-based selection
        else:
            search_limit = max((length or 12) * 3, 50)
        candidates = service.search_tracks(query, limit=search_limit)
        logger.debug(f"Found {len(candidates)} candidate tracks")

        if not candidates:
            logger.warning(f"No tracks found for search query: {query!r}")
            return QueueResult(
                mood_text=mood_text,
                mood_vector=vector,
                tracks=[],
                summary="No tracks found for this mood.",
            )

        # Build tracks using metadata-only (no audio-features endpoint)
        logger.info("Building queue using metadata-only mode (popularity, year, text heuristics)")
        metadata_tracks: List[QueueTrack] = []
        tracks_without_duration = 0
        for t in candidates:
            tid = t.get("id")
            name = t.get("name", "<unknown>")
            artists = ", ".join(a.get("name", "") for a in t.get("artists", []) or [])
            uri = t.get("uri") or (f"spotify:track:{tid}" if tid else "<unknown>")
            popularity = t.get("popularity")
            
            # Parse year from album.release_date if available
            album = t.get("album") or {}
            year_str = album.get("release_date") or ""
            year: Optional[int] = None
            if isinstance(year_str, str) and len(year_str) >= 4 and year_str[:4].isdigit():
                year = int(year_str[:4])

            duration_ms = t.get("duration_ms")
            if duration_ms is None:
                tracks_without_duration += 1

            # Use track + album name for text-based heuristics
            text = f"{name} {album.get('name', '')}"
            valence, energy = _metadata_valence_energy(vector, interpretation, popularity, year, text)

            metadata_tracks.append(
                QueueTrack(
                    name=name,
                    artists=artists,
                    uri=uri,
                    valence=valence,
                    energy=energy,
                    popularity=popularity,
                    year=year,
                    duration_ms=duration_ms,
                )
            )
        
        if tracks_without_duration > 0:
            logger.warning(f"Found {tracks_without_duration} tracks without duration_ms - duration-based selection may be inaccurate")
        if duration_minutes and duration_minutes > 0:
            tracks_with_duration = len(metadata_tracks) - tracks_without_duration
            logger.info(f"Duration mode: {tracks_with_duration}/{len(metadata_tracks)} tracks have duration_ms")

        # Metadata-based ranking:
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

        metadata_tracks.sort(key=meta_score, reverse=True)

        # Choose tracks either by count or by duration target.
        if duration_minutes and duration_minutes > 0:
            target_seconds = duration_minutes * 60
            tolerance = 3 * 60  # +/- 3 minutes
            selected: List[QueueTrack] = []

            # Use prefix-based selection honoring ranking priority (mood match first).
            # Evaluate prefixes to find the closest duration within tolerance; if none, pick closest overall.
            best_idx = 0
            best_diff = None
            best_within_tol = False
            total_seconds = 0
            
            logger.info(f"Duration-based selection: target={target_seconds}s ({duration_minutes} min), tolerance=±{tolerance}s")
            
            for idx, track in enumerate(metadata_tracks, start=1):
                dur_ms = track.duration_ms or 0
                dur_sec = max(0, int(dur_ms / 1000))
                total_seconds += dur_sec

                diff = abs(total_seconds - target_seconds)
                within_tol = total_seconds >= target_seconds - tolerance and total_seconds <= target_seconds + tolerance

                # Logic: Prefer solutions within tolerance. If we have one within tolerance, only update if new one is also within tolerance and better.
                # If we don't have one within tolerance yet, track the closest one.
                should_update = False
                if best_diff is None:
                    # First iteration - always take it
                    should_update = True
                elif within_tol and best_within_tol:
                    # Both within tolerance - pick the one closer to target
                    if diff < best_diff:
                        should_update = True
                elif within_tol and not best_within_tol:
                    # New one is within tolerance, old one wasn't - prefer the new one
                    should_update = True
                elif not within_tol and not best_within_tol:
                    # Neither within tolerance - pick the one closer to target
                    if diff < best_diff:
                        should_update = True

                if should_update:
                    best_idx = idx
                    best_diff = diff
                    best_within_tol = within_tol
                    
                # Log progress for debugging
                if idx <= 5 or idx % 10 == 0 or within_tol:
                    logger.debug(f"  Track {idx}: {track.name[:30]}... | dur={dur_sec}s | total={total_seconds}s | diff={diff}s | within_tol={within_tol}")

            if best_idx == 0:
                # Fallback: at least one track
                logger.warning("Duration selection found no tracks, using fallback (1 track)")
                best_idx = 1
            else:
                final_duration = sum((t.duration_ms or 0) / 1000 for t in metadata_tracks[:best_idx])
                logger.info(f"Selected {best_idx} tracks with total duration {final_duration:.1f}s ({final_duration/60:.1f} min), target was {target_seconds}s ({duration_minutes} min)")

            selected = metadata_tracks[:best_idx]
        else:
            selected = metadata_tracks[: max(1, length)]

        # Sort by energy for a gentle rise
        selected.sort(key=lambda t: t.energy)
        energy_range = (selected[0].energy, selected[-1].energy) if selected else (0.0, 0.0)
        logger.info(f"Metadata-only queue generated: {len(selected)} tracks, energy range: {energy_range[0]:.2f} - {energy_range[1]:.2f}")

        # Summary
        if selected:
            start_v = selected[0].valence
            end_v = selected[-1].valence
            total_ms = sum(t.duration_ms or 0 for t in selected)
            total_min = total_ms / 60000.0
            target_text = f"Target duration: {duration_minutes} min. " if duration_minutes else ""
            summary = (
                target_text +
                f"This queue starts at valence {start_v:.2f} and "
                f"moves toward {end_v:.2f} (energy rises gently). "
                f"Based on metadata-driven ranking (popularity, year, and text analysis). "
                f"Approx. total duration: {total_min:.1f} min."
            )
        else:
            summary = "Generated an empty queue."

        return QueueResult(
            mood_text=mood_text,
            mood_vector=vector,
            tracks=selected,
            summary=summary,
        )
    finally:
        service.close()


__all__ = ["QueueTrack", "QueueResult", "generate_queue"]


