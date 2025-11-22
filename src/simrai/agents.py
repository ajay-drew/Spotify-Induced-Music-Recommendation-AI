"""
Agent scaffolding for SIMRAI using CrewAI.

For now this module defines the four conceptual agents and a Crew that could
orchestrate them. In the 48-hour MVP, we still rely primarily on the
rule-based pipeline in `pipeline.py`; the Crew integration is a future
extension once an LLM is configured.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from crewai import Agent, Crew, Task
from langchain_core.language_models.chat_models import BaseChatModel

from .pipeline import QueueResult, generate_queue


@dataclass
class AgentConfig:
    llm: BaseChatModel


def build_agents(cfg: AgentConfig) -> list[Agent]:
    """
    Define the four conceptual agents for SIMRAI.
    """
    mood_alchemist = Agent(
        role="Mood Alchemist",
        goal="Interpret free-form human mood text into a precise musical mood vector.",
        backstory=(
            "You are an expert in affective computing and music psychology. "
            "You translate poetic, messy human mood descriptions into structured "
            "targets like valence and energy, plus a few keywords and artists."
        ),
        llm=cfg.llm,
        verbose=False,
    )

    seed_curator = Agent(
        role="Seed Curator",
        goal="Find diverse but coherent seed tracks for the desired mood.",
        backstory=(
            "You are a creative DJ who knows how to dig through Spotify-like "
            "catalogs to find tracks matching a given mood vector and seeds."
        ),
        llm=cfg.llm,
        verbose=False,
    )

    psychoacoustic_analyst = Agent(
        role="Psychoacoustic Analyst",
        goal="Score candidate tracks against the target mood profile.",
        backstory=(
            "You understand psychoacoustics and how valence, energy, and "
            "other features combine into an emotional feel for each track."
        ),
        llm=cfg.llm,
        verbose=False,
    )

    narrative_architect = Agent(
        role="Narrative Architect",
        goal="Arrange selected tracks into an emotional arc.",
        backstory=(
            "You design the emotional journey of a playlist: how it starts, "
            "builds, and resolves in a way that feels natural and compelling."
        ),
        llm=cfg.llm,
        verbose=False,
    )

    return [mood_alchemist, seed_curator, psychoacoustic_analyst, narrative_architect]


def build_crew(cfg: AgentConfig) -> Crew:
    """
    Build a CrewAI crew from the four agents.

    For now, the main task description simply references the mood-to-queue
    behavior, but the actual heavy lifting is still done by `generate_queue`.
    """
    agents = build_agents(cfg)
    task = Task(
        description=(
            "Given a user's mood description, collaborate to propose a Spotify "
            "queue: describe the target mood vector, the seed ideas, and the "
            "shape of the emotional arc. The SIMRAI code will turn this into "
            "a concrete queue using direct Spotify API calls."
        ),
        agents=agents,
    )
    return Crew(agents=agents, tasks=[task])


def run_with_agents(
    mood_text: str,
    *,
    length: int = 12,
    intense: bool = False,
    soft: bool = False,
    crew: Optional[Crew] = None,
) -> QueueResult:
    """
    Placeholder entrypoint to run SIMRAI with agents.

    In the current MVP, we simply delegate to the rule-based pipeline
    `generate_queue`. Once an LLM and Crew are fully configured, this function
    can first consult the Crew for refined mood interpretation and arc design,
    then feed that into a richer pipeline.
    """
    # Future: use crew.kickoff(...) to enrich the interpretation.
    _ = crew  # avoid unused argument warning for now
    return generate_queue(mood_text, length=length, intense=intense, soft=soft)


__all__ = ["AgentConfig", "build_agents", "build_crew", "run_with_agents"]


