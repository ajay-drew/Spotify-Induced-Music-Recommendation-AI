"""
Mood interpretation (Mood Alchemist v0).

For the 48-hour MVP we use a simple rule-based approach instead of an LLM:
- Map mood text + flags (--intense/--soft) to a target mood vector.
- Produce a few keyword seeds to drive Spotify search.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List


@dataclass
class MoodVector:
    valence: float  # 0.0–1.0, emotional positivity
    energy: float   # 0.0–1.0


@dataclass
class MoodInterpretation:
    vector: MoodVector
    search_terms: List[str]
    prefer_popular: bool = False
    prefer_obscure: bool = False
    prefer_recent: bool = False
    prefer_classics: bool = False


NEGATIVE_WORDS = {"sad", "cry", "lonely", "alone", "hurt", "broken", "melancholy", "melancholic"}
POSITIVE_WORDS = {"happy", "joy", "euphoric", "victory", "celebration", "party"}
LOW_ENERGY_WORDS = {"chill", "sleep", "calm", "midnight", "night", "late"}
HIGH_ENERGY_WORDS = {"hype", "rage", "workout", "gym", "dance", "party", "run"}

POPULAR_WORDS = {"hits", "popular", "mainstream", "bangers", "anthems"}
OBSCURE_WORDS = {"underground", "obscure", "deep", "rare", "b-sides", "b-sides"}
RECENT_WORDS = {"new", "recent", "latest", "fresh", "2020s", "2023", "2024", "2025"}
CLASSIC_WORDS = {"classic", "retro", "throwback", "old-school", "90s", "80s", "70s", "2000s"}


def clamp(value: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, value))


def interpret_mood(text: str, *, intense: bool = False, soft: bool = False) -> MoodInterpretation:
    """
    Very simple rule-based Mood Alchemist v0.

    - Starts from a neutral vector (0.5, 0.5).
    - Adjusts based on keywords and flags.
    - Returns a MoodInterpretation with vector and search terms.
    """
    base_valence = 0.5
    base_energy = 0.5

    lowered = text.lower()
    tokens = set(lowered.replace(",", " ").split())

    # Adjust valence.
    if tokens & NEGATIVE_WORDS:
        base_valence -= 0.2
    if tokens & POSITIVE_WORDS:
        base_valence += 0.2

    # Adjust energy.
    if tokens & LOW_ENERGY_WORDS:
        base_energy -= 0.2
    if tokens & HIGH_ENERGY_WORDS:
        base_energy += 0.2

    # Flags.
    if intense:
        base_energy += 0.2
        base_valence += 0.05  # slight push toward more vivid moods
    if soft:
        base_energy -= 0.2
        base_valence -= 0.05  # tilt slightly toward introspective

    vector = MoodVector(
        valence=clamp(base_valence),
        energy=clamp(base_energy),
    )

    # Very naive search terms: original text plus a few mood words.
    search_terms: List[str] = [text]
    if intense:
        search_terms.append("intense")
    if soft:
        search_terms.append("acoustic")
        search_terms.append("chill")

    # Metadata preferences inferred from wording.
    prefer_popular = bool(tokens & POPULAR_WORDS)
    prefer_obscure = bool(tokens & OBSCURE_WORDS)
    prefer_recent = bool(tokens & RECENT_WORDS)
    prefer_classics = bool(tokens & CLASSIC_WORDS)

    return MoodInterpretation(
        vector=vector,
        search_terms=search_terms,
        prefer_popular=prefer_popular,
        prefer_obscure=prefer_obscure,
        prefer_recent=prefer_recent,
        prefer_classics=prefer_classics,
    )


__all__ = ["MoodVector", "MoodInterpretation", "interpret_mood"]


