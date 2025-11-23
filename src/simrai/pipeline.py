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

# is_ai_available is imported lazily inside generate_queue to avoid circular imports
# Tests can patch simrai.agents.is_ai_available directly, or patch this module's
# _is_ai_available function after the module loads
def _is_ai_available():
    """Lazy wrapper for is_ai_available to avoid circular imports."""
    from .agents import is_ai_available
    return is_ai_available()

# Export for tests - they can patch this function
is_ai_available = _is_ai_available


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

    Automatically attempts AI enhancement if available, falls back to rule-based silently.
    """
    logger.info(f"Generating queue for mood: {mood_text!r} (length={length}, intense={intense}, soft={soft})")
    
    # Try AI enhancement if available, fallback to rule-based
    try:
        from .agents import AgentConfig, build_crew, create_groq_llm, is_ai_available as _check_ai, run_with_agents

        if _check_ai():
            logger.info("AI enhancement available, attempting agent-based queue generation")
            llm = create_groq_llm()
            if llm:
                logger.debug(f"Created Groq LLM: {type(llm).__name__}")
                cfg = AgentConfig(llm=llm)
                crew = build_crew(cfg)
                logger.debug("Crew built successfully, running with agents")
                result = run_with_agents(
                    mood_text,
                    length=length,
                    intense=intense,
                    soft=soft,
                    crew=crew,
                )
                logger.info(f"AI-enhanced queue generated: {len(result.tracks)} tracks")
                return result
            else:
                logger.warning("Failed to create Groq LLM instance")
    except Exception as exc:
        # Silently fall back to rule-based on any error
        logger.warning(f"AI enhancement failed, falling back to rule-based: {exc}")

    # Rule-based fallback
    logger.debug("Using rule-based mood interpretation")
    interpretation: MoodInterpretation = interpret_mood(mood_text, intense=intense, soft=soft)
    vector = interpretation.vector
    logger.debug(f"Mood vector: valence={vector.valence:.2f}, energy={vector.energy:.2f}, search_terms={interpretation.search_terms}")

    service = SpotifyService()
    try:
        # Search for candidate tracks using mood interpretation
        query = " ".join(interpretation.search_terms)
        logger.info(f"Searching Spotify for: {query!r}")
        candidates = service.search_tracks(query, limit=max(length * 3, 40))
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
                )
            )

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
        selected = metadata_tracks[: max(1, length)]
        
        # Sort by energy for a gentle rise
        selected.sort(key=lambda t: t.energy)
        logger.info(f"Metadata-only queue generated: {len(selected)} tracks, energy range: {selected[0].energy:.2f} - {selected[-1].energy:.2f}")

        # Summary
        if selected:
            start_v = selected[0].valence
            end_v = selected[-1].valence
            summary = (
                f"This queue starts at valence {start_v:.2f} and "
                f"moves toward {end_v:.2f} (energy rises gently). "
                f"Based on metadata-driven ranking (popularity, year, and text analysis)."
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


