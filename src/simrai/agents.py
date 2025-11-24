"""
Lightweight AI helpers for SIMRAI (no CrewAI).

SIMRAI now relies on a **metadata-first, Groq-backed pipeline**:
- `simrai.mood.interpret_mood` does rule-based mood interpretation and optionally
  calls Groq (if `GROQ_API_KEY` is set) to refine the mood vector and search terms.
- `simrai.pipeline.generate_queue` builds the queue purely from Spotify metadata.

This module exists only to preserve a stable import surface (`simrai.agents`)
for any external code or tests that might still import it. It does **not** use
CrewAI, LangChain, or agent orchestration.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .pipeline import QueueResult, generate_queue


@dataclass
class AgentConfig:
    """
    Backwards-compatibility stub for the old AI agent configuration.

    Historically this carried a LangChain / Groq LLM instance; now it is
    optional and unused, but kept so existing imports continue to work.
    """

    llm: Optional[object] = None


def is_ai_available() -> bool:
    """
    Backwards-compatible stub indicating whether complex agent AI is available.

    Since SIMRAI no longer uses a CrewAI-based agent framework, this always
    returns False. The only AI in use is the optional Groq-backed enhancement
    inside `interpret_mood`, which does not depend on this flag.
    """

    return False


def run_with_agents(
    mood_text: str,
    *,
    length: int = 12,
    intense: bool = False,
    soft: bool = False,
    crew: object | None = None,  # kept only for signature compatibility
) -> QueueResult:
    """
    Backwards-compatible wrapper that simply delegates to `generate_queue`.

    Parameters mirror the old agent entrypoint so callers don't break, but
    internally this just runs the standard metadata-first pipeline.
    """

    return generate_queue(mood_text, length=length, intense=intense, soft=soft)


__all__ = ["AgentConfig", "is_ai_available", "run_with_agents"]



