"""
Agent scaffolding for SIMRAI using CrewAI and LangChain Groq integration.

This module provides OSS LLM integration via Groq-hosted models (e.g., Llama 3)
using LangChain, wired into CrewAI agents for enhanced mood interpretation.
"""

from __future__ import annotations

import json
import logging
import os
import socket
from dataclasses import dataclass
from typing import Optional

from crewai import Agent, Crew, Task
from langchain_core.language_models.chat_models import BaseChatModel

from .mood import MoodInterpretation, MoodVector, interpret_mood
from .pipeline import QueueResult, generate_queue

logger = logging.getLogger(__name__)

try:
    from langchain_groq import ChatGroq
except ImportError:
    ChatGroq = None  # type: ignore[assignment, misc]


@dataclass
class AgentConfig:
    llm: BaseChatModel


def _check_network_connectivity() -> bool:
    """
    Check if network connectivity is available by attempting to reach a reliable endpoint.

    Returns:
        True if network is available, False otherwise.
    """
    try:
        # Try to connect to a reliable DNS server (Google's 8.8.8.8)
        socket.create_connection(("8.8.8.8", 53), timeout=2)
        logger.debug("Network connectivity check passed")
        return True
    except (OSError, socket.timeout, socket.gaierror) as exc:
        logger.debug(f"Network connectivity check failed: {exc}")
        return False


def _check_groq_availability() -> bool:
    """
    Check if Groq API is available and configured.

    Returns:
        True if Groq is available and configured, False otherwise.
    """
    if ChatGroq is None:
        return False

    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        return False

    # Quick check: try to create an LLM instance (doesn't make network call)
    try:
        model = os.getenv("SIMRAI_GROQ_MODEL", "llama-3.1-8b-instant")
        # Just check if we can instantiate, don't actually call API
        llm = ChatGroq(
            model=model,
            temperature=0.3,
            groq_api_key=api_key,
        )
        return llm is not None
    except Exception:
        return False


def is_ai_available() -> bool:
    """
    Check if AI enhancement is available (network + Groq configured).

    Returns:
        True if both network and Groq are available, False otherwise.
    """
    if not _check_network_connectivity():
        logger.debug("AI not available: network connectivity check failed")
        return False
    groq_available = _check_groq_availability()
    if groq_available:
        logger.debug("AI enhancement available (network + Groq configured)")
    else:
        logger.debug("AI not available: Groq not configured or unavailable")
    return groq_available


def create_groq_llm(
    *,
    model: Optional[str] = None,
    temperature: float = 0.3,
    api_key: Optional[str] = None,
) -> Optional[BaseChatModel]:
    """
    Create a Groq-hosted LLM via LangChain.

    Args:
        model: Model name (defaults to SIMRAI_GROQ_MODEL env var or "llama-3.1-8b-instant")
        temperature: Sampling temperature (0.0-1.0)
        api_key: Groq API key (defaults to GROQ_API_KEY env var)

    Returns:
        ChatGroq instance if available, None otherwise.
    """
    if ChatGroq is None:
        logger.warning("ChatGroq is not available (langchain-groq not installed)")
        return None

    api_key = api_key or os.getenv("GROQ_API_KEY")
    if not api_key:
        logger.warning("GROQ_API_KEY not set")
        return None

    model = model or os.getenv("SIMRAI_GROQ_MODEL", "llama-3.1-8b-instant")
    logger.debug(f"Creating Groq LLM: model={model}")

    try:
        llm = ChatGroq(
            model=model,
            temperature=temperature,
            groq_api_key=api_key,
        )
        logger.info(f"Successfully created Groq LLM: {model}")
        return llm
    except Exception as exc:
        logger.error(f"Failed to create Groq LLM: {exc}")
        return None


def build_agents(cfg: AgentConfig) -> list[Agent]:
    """
    Define the four conceptual agents for SIMRAI.
    """
    if cfg.llm is None:
        logger.error("Cannot build agents: LLM is None")
        raise ValueError("LLM must be provided in AgentConfig")
    
    logger.info("Building CrewAI agents for mood interpretation")
    logger.debug(f"Agent LLM type: {type(cfg.llm).__name__}, class: {cfg.llm.__class__.__module__}.{cfg.llm.__class__.__name__}")
    
    # Ensure LLM is properly set - CrewAI needs explicit LLM to avoid OpenAI default
    mood_alchemist = Agent(
        role="Mood Alchemist",
        goal="Interpret free-form human mood text into a precise musical mood vector.",
        backstory=(
            "You are an expert in affective computing and music psychology. "
            "You translate poetic, messy human mood descriptions into structured "
            "targets like valence (0-1, emotional positivity) and energy (0-1, intensity), "
            "plus search keywords and metadata preferences. "
            "Output your interpretation as JSON with fields: valence, energy, search_terms (list), "
            "prefer_popular, prefer_obscure, prefer_recent, prefer_classics (all booleans)."
        ),
        llm=cfg.llm,  # Explicitly pass Groq LLM
        verbose=False,
        allow_delegation=False,
        max_iter=3,  # Limit iterations to avoid long runs
    )

    seed_curator = Agent(
        role="Seed Curator",
        goal="Suggest diverse but coherent seed search terms for the desired mood.",
        backstory=(
            "You are a creative DJ who knows how to dig through Spotify-like "
            "catalogs. Given a mood vector, suggest 5-10 specific search terms "
            "that would help find tracks matching that emotional profile. "
            "Output as JSON with a 'search_terms' list."
        ),
        llm=cfg.llm,  # Explicitly pass Groq LLM
        verbose=False,
        allow_delegation=False,
        max_iter=3,
    )

    psychoacoustic_analyst = Agent(
        role="Psychoacoustic Analyst",
        goal="Validate and refine mood vector based on music theory.",
        backstory=(
            "You understand psychoacoustics and how valence, energy, and "
            "other features combine into an emotional feel. Review the proposed "
            "mood vector and suggest refinements if needed. Output as JSON with "
            "valence and energy fields."
        ),
        llm=cfg.llm,  # Explicitly pass Groq LLM
        verbose=False,
        allow_delegation=False,
        max_iter=3,
    )

    narrative_architect = Agent(
        role="Narrative Architect",
        goal="Design the emotional arc for the playlist.",
        backstory=(
            "You design the emotional journey of a playlist: how it starts, "
            "builds, and resolves. Given a mood vector, suggest how the energy "
            "and valence should evolve across the queue. Output as JSON with "
            "optional 'arc_description' text field."
        ),
        llm=cfg.llm,  # Explicitly pass Groq LLM
        verbose=False,
        allow_delegation=False,
        max_iter=3,
    )

    agents = [mood_alchemist, seed_curator, psychoacoustic_analyst, narrative_architect]
    logger.debug(f"Built {len(agents)} CrewAI agents")
    return agents


def build_crew(cfg: AgentConfig) -> Crew:
    """
    Build a CrewAI crew from the four agents.

    The crew collaborates to refine mood interpretation, with the Mood Alchemist
    taking the lead and other agents providing validation and suggestions.
    """
    logger.info("Building CrewAI crew with Groq LLM")
    
    # Ensure LLM is properly configured
    if cfg.llm is None:
        logger.error("Cannot build crew: LLM is None")
        raise ValueError("LLM must be provided in AgentConfig")
    
    # Log LLM type for debugging
    logger.debug(f"Using LLM type: {type(cfg.llm).__name__}")
    
    agents = build_agents(cfg)

    # Primary task: mood interpretation
    mood_task = Task(
        description=(
            "Interpret the user's mood description into a precise mood vector. "
            "Consider the emotional tone, energy level, and any explicit preferences. "
            "Output a JSON object with: valence (0-1), energy (0-1), search_terms (list), "
            "and preference flags (prefer_popular, prefer_obscure, prefer_recent, prefer_classics)."
        ),
        agent=agents[0],  # Mood Alchemist
        expected_output="JSON object with mood vector and search terms",
    )

    # Secondary task: validate and enhance
    validation_task = Task(
        description=(
            "Review the mood interpretation and suggest any refinements. "
            "Consider music theory and psychoacoustic principles. "
            "Output JSON with any adjustments to valence, energy, or search terms."
        ),
        agent=agents[2],  # Psychoacoustic Analyst
        expected_output="JSON object with refined mood vector",
    )

    # Pass LLM to Crew to ensure it uses Groq instead of defaulting to OpenAI
    # CrewAI will use this LLM for all agents if they don't have their own
    # Setting verbose=True temporarily to debug LLM usage
    try:
        crew = Crew(
            agents=agents,
            tasks=[mood_task, validation_task],
            llm=cfg.llm,  # Explicitly set LLM at Crew level to prevent OpenAI default
            verbose=False,
            process="sequential",  # Use sequential process to avoid delegation issues
        )
        logger.debug("CrewAI crew built successfully with Groq LLM")
    except Exception as exc:
        logger.error(f"Failed to build CrewAI crew: {exc}")
        logger.debug(f"LLM details: type={type(cfg.llm)}, module={cfg.llm.__class__.__module__}")
        raise
    logger.debug("CrewAI crew built successfully with Groq LLM")
    return crew


def _parse_agent_output(text: str) -> Optional[dict]:
    """
    Parse JSON output from agent responses.

    Agents may return JSON wrapped in markdown code blocks or plain text.
    """
    if not text:
        return None

    # Try to extract JSON from markdown code blocks
    if "```json" in text:
        start = text.find("```json") + 7
        end = text.find("```", start)
        if end > start:
            text = text[start:end].strip()
    elif "```" in text:
        start = text.find("```") + 3
        end = text.find("```", start)
        if end > start:
            text = text[start:end].strip()

    # Try to find JSON object boundaries
    start_brace = text.find("{")
    end_brace = text.rfind("}")
    if start_brace >= 0 and end_brace > start_brace:
        text = text[start_brace : end_brace + 1]

    try:
        data = json.loads(text)
        if isinstance(data, dict):
            return data
    except json.JSONDecodeError:
        pass

    return None


def _enhance_mood_with_agents(
    mood_text: str,
    *,
    intense: bool,
    soft: bool,
    crew: Crew,
) -> Optional[MoodInterpretation]:
    """
    Use CrewAI agents to enhance mood interpretation.

    Returns an enhanced MoodInterpretation if successful, None to fall back to rule-based.
    """
    prompt = (
        f"Mood description: {mood_text!r}\n"
        f"Flags: intense={intense}, soft={soft}\n"
        "Interpret this mood and output JSON with valence, energy, search_terms, "
        "and preference flags."
    )

    try:
        logger.info(f"Running CrewAI crew for mood enhancement: {mood_text!r}")
        result = crew.kickoff(inputs={"mood": mood_text, "intense": intense, "soft": soft})
        # CrewAI returns a CrewOutput object; extract the text
        output_text = str(result) if result else ""
        logger.debug(f"CrewAI output received: {len(output_text)} characters")

        # Try to parse JSON from the output
        parsed = _parse_agent_output(output_text)
        if not parsed:
            logger.warning("Failed to parse JSON from CrewAI output")
            # Fallback: try parsing each agent's output separately
            # (CrewAI may return structured output)
            return None

        # Extract values with defaults
        valence = float(parsed.get("valence", 0.5))
        energy = float(parsed.get("energy", 0.5))
        search_terms = parsed.get("search_terms", [])
        if not isinstance(search_terms, list):
            search_terms = [mood_text]

        # Ensure search terms include the original mood
        if mood_text not in search_terms:
            search_terms.insert(0, mood_text)

        interpretation = MoodInterpretation(
            vector=MoodVector(
                valence=max(0.0, min(1.0, valence)),
                energy=max(0.0, min(1.0, energy)),
            ),
            search_terms=search_terms[:10],  # Limit to 10 terms
            prefer_popular=parsed.get("prefer_popular", False),
            prefer_obscure=parsed.get("prefer_obscure", False),
            prefer_recent=parsed.get("prefer_recent", False),
            prefer_classics=parsed.get("prefer_classics", False),
        )
        logger.info(f"CrewAI mood enhancement successful: valence={interpretation.vector.valence:.2f}, energy={interpretation.vector.energy:.2f}")
        return interpretation
    except Exception as exc:
        # Any error: fall back to rule-based
        logger.warning(f"CrewAI mood enhancement failed: {exc}, falling back to rule-based")
        return None


def run_with_agents(
    mood_text: str,
    *,
    length: int = 12,
    intense: bool = False,
    soft: bool = False,
    crew: Optional[Crew] = None,
) -> QueueResult:
    """
    Run SIMRAI with CrewAI agent enhancement, falling back to rule-based if agents fail.

    If a crew is provided, attempts to use agents for enhanced interpretation.
    Falls back silently to rule-based pipeline on any error.
    """
    if crew:
        logger.info("Running pipeline with CrewAI agent enhancement")
        enhanced = _enhance_mood_with_agents(mood_text, intense=intense, soft=soft, crew=crew)
        if enhanced:
            # Temporarily override interpret_mood to return the enhanced interpretation
            import simrai.mood as mood_mod
            original_interpret = mood_mod.interpret_mood

            def enhanced_interpret(text: str, *, intense: bool, soft: bool) -> MoodInterpretation:
                # Use enhanced interpretation for the exact same input
                if text == mood_text:
                    return enhanced
                return original_interpret(text, intense=intense, soft=soft)

            mood_mod.interpret_mood = enhanced_interpret
            try:
                result = generate_queue(mood_text, length=length, intense=intense, soft=soft)
                return result
            finally:
                # Restore original function
                mood_mod.interpret_mood = original_interpret

    # Fallback to standard pipeline
    return generate_queue(mood_text, length=length, intense=intense, soft=soft)


__all__ = [
    "AgentConfig",
    "build_agents",
    "build_crew",
    "run_with_agents",
    "create_groq_llm",
    "is_ai_available",
]
