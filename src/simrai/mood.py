"""
Mood interpretation (Mood Alchemist v0).

For the 48-hour MVP we use a simple rule-based approach instead of an LLM:
- Map mood text + flags (--intense/--soft) to a target mood vector.
- Produce a few keyword seeds to drive Spotify search.
"""

from __future__ import annotations

import json
import logging
import os
from collections import deque
from dataclasses import dataclass
from time import time
from typing import Any, Deque, Dict, List, Optional

logger = logging.getLogger(__name__)


try:
    # Optional: will be available once requirements are installed.
    from groq import Groq
except Exception:  # pragma: no cover - missing dependency is handled gracefully
    Groq = None  # type: ignore[assignment]


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

_GROQ_CALL_TIMES: Deque[float] = deque()
_GROQ_MAX_CALLS_PER_MINUTE = max(
    1,
    int(os.getenv("SIMRAI_GROQ_MAX_CALLS_PER_MINUTE", "20")),
)


def clamp(value: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, value))


def _can_call_groq() -> bool:
    """Simple in-process rate limiter to stay under a safe free-tier budget."""
    now = time()
    # Drop timestamps older than 60 seconds.
    while _GROQ_CALL_TIMES and now - _GROQ_CALL_TIMES[0] > 60:
        _GROQ_CALL_TIMES.popleft()
    if len(_GROQ_CALL_TIMES) >= _GROQ_MAX_CALLS_PER_MINUTE:
        logger.warning(f"Groq rate limit reached: {len(_GROQ_CALL_TIMES)} calls in the last minute (max: {_GROQ_MAX_CALLS_PER_MINUTE})")
        return False
    _GROQ_CALL_TIMES.append(now)
    return True


def _call_groq_mood_ai(
    text: str,
    *,
    intense: bool,
    soft: bool,
) -> Optional[Dict[str, Any]]:
    """
    Call a Groq-hosted open-source model (e.g., Llama 3 / Mixtral) to refine
    the mood vector and seeds.

    The model is configured via:
    - GROQ_API_KEY          (required for calls)
    - SIMRAI_GROQ_MODEL     (optional, default is an OSS model name)
    - SIMRAI_GROQ_MAX_CALLS_PER_MINUTE (rate limiting, default 20)

    Returns a small dict with optional keys:
    - valence (float 0–1)
    - energy (float 0–1)
    - search_terms (list[str])
    - prefer_popular / prefer_obscure / prefer_recent / prefer_classics (bool)
    """
    if Groq is None:
        return None

    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        return None

    if not _can_call_groq():
        # Soft-fail: stay under free-tier by skipping LLM when over budget.
        return None

    model = os.getenv("SIMRAI_GROQ_MODEL", "llama-3.1-8b-instant")
    logger.debug(f"Calling Groq API for mood interpretation: model={model}")

    # Compose a compact, JSON-only instruction to keep parsing robust.
    system_prompt = (
        "You are a mood-to-music assistant. Given a short mood description and flags "
        "for intense/soft, you output ONLY a single JSON object with fields: "
        "{"
        '"valence": float between 0 and 1, '
        '"energy": float between 0 and 1, '
        '"search_terms": list of 3-8 short phrases for music search, '
        '"prefer_popular": bool, '
        '"prefer_obscure": bool, '
        '"prefer_recent": bool, '
        '"prefer_classics": bool'
        "}. No explanation, no markdown, just JSON."
    )
    user_prompt = json.dumps(
        {
            "mood": text,
            "intense": intense,
            "soft": soft,
        }
    )

    try:
        client = Groq(api_key=api_key)
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.3,
            max_tokens=256,
        )
        choice = resp.choices[0].message.content if resp.choices else ""
        if not choice:
            logger.debug("Groq API returned empty response")
            return None
        data = json.loads(choice)
        if not isinstance(data, dict):
            logger.debug("Groq API response is not a dict")
            return None
        logger.info(f"Groq AI mood interpretation successful: valence={data.get('valence')}, energy={data.get('energy')}")
        return data
    except Exception as exc:
        # Any Groq/network/JSON error: quietly fall back to rule-based logic.
        logger.warning(f"Groq API call failed, falling back to rule-based: {exc}")
        return None


def interpret_mood(text: str, *, intense: bool = False, soft: bool = False) -> MoodInterpretation:
    """
    Mood Alchemist v0 with optional Groq-powered enhancement.

    - Always starts from a simple rule-based heuristic (no network needed).
    - If GROQ_API_KEY is set and rate limits allow, asks a Groq OSS model
      (configured via SIMRAI_GROQ_MODEL) to refine valence/energy, search
      terms, and metadata preferences.
    - Falls back gracefully to pure rule-based behavior on any error.
    """
    logger.info(f"Processing mood: {text!r} (intense={intense}, soft={soft})")
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

    # Base metadata preferences inferred from wording.
    prefer_popular = bool(tokens & POPULAR_WORDS)
    prefer_obscure = bool(tokens & OBSCURE_WORDS)
    prefer_recent = bool(tokens & RECENT_WORDS)
    prefer_classics = bool(tokens & CLASSIC_WORDS)

    # Optional Groq AI refinement.
    ai_data = _call_groq_mood_ai(text, intense=intense, soft=soft)
    if ai_data:
        logger.debug("Applying AI-enhanced mood interpretation")
        # Override valence/energy if present.
        v = ai_data.get("valence")
        e = ai_data.get("energy")
        if isinstance(v, (int, float)):
            base_valence = float(v)
        if isinstance(e, (int, float)):
            base_energy = float(e)

        # Override metadata preferences where provided.
        for key in ("prefer_popular", "prefer_obscure", "prefer_recent", "prefer_classics"):
            if key in ai_data and isinstance(ai_data[key], bool):
                if key == "prefer_popular":
                    prefer_popular = ai_data[key]
                elif key == "prefer_obscure":
                    prefer_obscure = ai_data[key]
                elif key == "prefer_recent":
                    prefer_recent = ai_data[key]
                elif key == "prefer_classics":
                    prefer_classics = ai_data[key]

    vector = MoodVector(
        valence=clamp(base_valence),
        energy=clamp(base_energy),
    )

    # Base search terms: original text plus a few mood words.
    search_terms: List[str] = [text]
    if intense:
        search_terms.append("intense")
    if soft:
        search_terms.append("acoustic")
        search_terms.append("chill")

    # Add AI-suggested search terms if available.
    if ai_data:
        extra_terms = ai_data.get("search_terms")
        if isinstance(extra_terms, list):
            for term in extra_terms:
                if isinstance(term, str) and term.strip():
                    search_terms.append(term.strip())

    interpretation = MoodInterpretation(
        vector=vector,
        search_terms=search_terms,
        prefer_popular=prefer_popular,
        prefer_obscure=prefer_obscure,
        prefer_recent=prefer_recent,
        prefer_classics=prefer_classics,
    )
    logger.info(f"Mood interpretation complete: valence={vector.valence:.2f}, energy={vector.energy:.2f}, search_terms={len(search_terms)}")
    return interpretation


__all__ = ["MoodVector", "MoodInterpretation", "interpret_mood"]


