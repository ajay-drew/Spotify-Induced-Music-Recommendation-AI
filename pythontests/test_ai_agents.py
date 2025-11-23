"""
Comprehensive tests for AI agent integration and fallback behavior.

Tests:
- AI availability checks (network, Groq)
- Agent initialization
- Agent mood enhancement
- Fallback to rule-based when AI unavailable
- Error handling in agent pipeline
"""

from __future__ import annotations

import json
import os
from unittest.mock import MagicMock, patch, create_autospec, create_autospec

import pytest

from simrai.agents import (
    AgentConfig,
    _check_groq_availability,
    _check_network_connectivity,
    _enhance_mood_with_agents,
    _parse_agent_output,
    build_agents,
    build_crew,
    create_groq_llm,
    is_ai_available,
    run_with_agents,
)
from simrai.mood import MoodInterpretation, MoodVector
from simrai.pipeline import QueueResult, generate_queue


def _create_mock_llm():
    """Create a mock LLM that satisfies CrewAI's Pydantic validation."""
    from langchain_core.language_models.chat_models import BaseChatModel
    # Use create_autospec to create a mock with the right interface
    mock_llm = create_autospec(BaseChatModel, instance=True)
    # Don't set model_name - CrewAI will try to infer provider from it
    return mock_llm


@pytest.fixture(autouse=True)
def reset_env(monkeypatch) -> None:
    """Reset environment variables before each test."""
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.delenv("SIMRAI_GROQ_MODEL", raising=False)


def test_check_network_connectivity_success(monkeypatch) -> None:
    """Test network connectivity check when network is available."""
    mock_socket = MagicMock()
    mock_socket.create_connection.return_value = None
    monkeypatch.setattr("simrai.agents.socket.create_connection", mock_socket.create_connection)

    assert _check_network_connectivity() is True


def test_check_network_connectivity_failure(monkeypatch) -> None:
    """Test network connectivity check when network is unavailable."""
    mock_socket = MagicMock()
    mock_socket.create_connection.side_effect = OSError("No network")
    monkeypatch.setattr("simrai.agents.socket.create_connection", mock_socket.create_connection)

    assert _check_network_connectivity() is False


def test_check_groq_availability_no_api_key(monkeypatch) -> None:
    """Test Groq availability check when API key is missing."""
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    assert _check_groq_availability() is False


def test_check_groq_availability_with_api_key(monkeypatch) -> None:
    """Test Groq availability check when API key is present."""
    monkeypatch.setenv("GROQ_API_KEY", "test-key")

    with patch("simrai.agents.ChatGroq") as mock_groq:
        mock_llm = _create_mock_llm()
        mock_groq.return_value = mock_llm
        assert _check_groq_availability() is True


def test_check_groq_availability_import_error(monkeypatch) -> None:
    """Test Groq availability check when langchain_groq is not installed."""
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    monkeypatch.setattr("simrai.agents.ChatGroq", None)

    assert _check_groq_availability() is False


def test_is_ai_available_no_network(monkeypatch) -> None:
    """Test AI availability when network is down."""
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    mock_socket = MagicMock()
    mock_socket.create_connection.side_effect = OSError("No network")
    monkeypatch.setattr("simrai.agents.socket.create_connection", mock_socket.create_connection)

    assert is_ai_available() is False


def test_is_ai_available_no_groq_key(monkeypatch) -> None:
    """Test AI availability when Groq API key is missing."""
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    mock_socket = MagicMock()
    mock_socket.create_connection.return_value = None
    monkeypatch.setattr("simrai.agents.socket.create_connection", mock_socket.create_connection)

    assert is_ai_available() is False


def test_is_ai_available_success(monkeypatch) -> None:
    """Test AI availability when both network and Groq are available."""
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    mock_socket = MagicMock()
    mock_socket.create_connection.return_value = None
    monkeypatch.setattr("simrai.agents.socket.create_connection", mock_socket.create_connection)

    with patch("simrai.agents.ChatGroq") as mock_groq:
        mock_llm = _create_mock_llm()
        mock_groq.return_value = mock_llm
        assert is_ai_available() is True


def test_create_groq_llm_success(monkeypatch) -> None:
    """Test creating a Groq LLM instance."""
    monkeypatch.setenv("GROQ_API_KEY", "test-key")

    with patch("simrai.agents.ChatGroq") as mock_groq:
        mock_llm = _create_mock_llm()
        mock_groq.return_value = mock_llm

        llm = create_groq_llm()
        assert llm is not None
        mock_groq.assert_called_once()


def test_create_groq_llm_no_api_key(monkeypatch) -> None:
    """Test creating Groq LLM without API key."""
    monkeypatch.delenv("GROQ_API_KEY", raising=False)

    llm = create_groq_llm()
    assert llm is None


def test_create_groq_llm_custom_model(monkeypatch) -> None:
    """Test creating Groq LLM with custom model."""
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    monkeypatch.setenv("SIMRAI_GROQ_MODEL", "llama-3.3-70b-versatile")

    with patch("simrai.agents.ChatGroq") as mock_groq:
        mock_llm = _create_mock_llm()
        mock_groq.return_value = mock_llm

        llm = create_groq_llm()
        assert llm is not None
        # Verify model was passed
        call_kwargs = mock_groq.call_args[1]
        assert call_kwargs["model"] == "llama-3.3-70b-versatile"


def test_parse_agent_output_json() -> None:
    """Test parsing JSON from agent output."""
    output = '{"valence": 0.7, "energy": 0.6, "search_terms": ["test"]}'
    parsed = _parse_agent_output(output)
    assert parsed is not None
    assert parsed["valence"] == 0.7
    assert parsed["energy"] == 0.6


def test_parse_agent_output_markdown_code_block() -> None:
    """Test parsing JSON from markdown code block."""
    output = '```json\n{"valence": 0.8, "energy": 0.5}\n```'
    parsed = _parse_agent_output(output)
    assert parsed is not None
    assert parsed["valence"] == 0.8


def test_parse_agent_output_invalid_json() -> None:
    """Test parsing invalid JSON returns None."""
    output = "This is not JSON"
    parsed = _parse_agent_output(output)
    assert parsed is None


def test_parse_agent_output_empty() -> None:
    """Test parsing empty output returns None."""
    parsed = _parse_agent_output("")
    assert parsed is None


def test_build_agents(monkeypatch) -> None:
    """Test building CrewAI agents."""
    monkeypatch.setenv("GROQ_API_KEY", "test-key")

    with patch("simrai.agents.ChatGroq") as mock_groq, patch(
        "crewai.utilities.llm_utils.create_llm"
    ) as mock_create_llm, patch("crewai.llm.LLM.__new__") as mock_llm_new:
        mock_llm = _create_mock_llm()
        mock_groq.return_value = mock_llm
        # CrewAI wraps LLMs - return our mock directly
        mock_create_llm.side_effect = lambda llm: llm
        # Also patch LLM.__new__ to return our mock if called
        mock_llm_new.side_effect = lambda cls, *args, **kwargs: mock_llm

        llm = create_groq_llm()
        assert llm is not None

        cfg = AgentConfig(llm=llm)
        agents = build_agents(cfg)

        assert len(agents) == 4
        assert agents[0].role == "Mood Alchemist"
        assert agents[1].role == "Seed Curator"
        assert agents[2].role == "Psychoacoustic Analyst"
        assert agents[3].role == "Narrative Architect"


def test_build_crew(monkeypatch) -> None:
    """Test building CrewAI crew."""
    monkeypatch.setenv("GROQ_API_KEY", "test-key")

    with patch("simrai.agents.ChatGroq") as mock_groq, patch(
        "crewai.utilities.llm_utils.create_llm"
    ) as mock_create_llm, patch("crewai.llm.LLM.__new__") as mock_llm_new:
        mock_llm = _create_mock_llm()
        mock_groq.return_value = mock_llm
        mock_create_llm.side_effect = lambda llm: llm
        mock_llm_new.side_effect = lambda cls, *args, **kwargs: mock_llm

        llm = create_groq_llm()
        cfg = AgentConfig(llm=llm)
        crew = build_crew(cfg)

        assert crew is not None
        assert len(crew.agents) == 4
        assert len(crew.tasks) == 2


def test_enhance_mood_with_agents_success(monkeypatch) -> None:
    """Test successful mood enhancement via agents."""
    monkeypatch.setenv("GROQ_API_KEY", "test-key")

    with patch("simrai.agents.ChatGroq") as mock_groq, patch(
        "crewai.utilities.llm_utils.create_llm"
    ) as mock_create_llm, patch("crewai.llm.LLM.__new__") as mock_llm_new:
        mock_llm = _create_mock_llm()
        mock_groq.return_value = mock_llm
        mock_create_llm.side_effect = lambda llm: llm
        mock_llm_new.side_effect = lambda cls, *args, **kwargs: mock_llm

        llm = create_groq_llm()
        cfg = AgentConfig(llm=llm)
        crew = build_crew(cfg)

        # Mock crew.kickoff to return valid JSON - patch at class level since Crew is Pydantic
        mock_result = MagicMock()
        mock_result.__str__ = lambda x: '{"valence": 0.75, "energy": 0.65, "search_terms": ["enhanced", "mood"]}'
        with patch("crewai.crew.Crew.kickoff", return_value=mock_result):
            enhanced = _enhance_mood_with_agents("test mood", intense=False, soft=False, crew=crew)

        assert enhanced is not None
        assert enhanced.vector.valence == 0.75
        assert enhanced.vector.energy == 0.65
        assert "enhanced" in enhanced.search_terms


def test_enhance_mood_with_agents_failure(monkeypatch) -> None:
    """Test mood enhancement fallback when agents fail."""
    monkeypatch.setenv("GROQ_API_KEY", "test-key")

    with patch("simrai.agents.ChatGroq") as mock_groq, patch(
        "crewai.utilities.llm_utils.create_llm"
    ) as mock_create_llm, patch("crewai.llm.LLM.__new__") as mock_llm_new:
        mock_llm = _create_mock_llm()
        mock_groq.return_value = mock_llm
        mock_create_llm.side_effect = lambda llm: llm
        mock_llm_new.side_effect = lambda cls, *args, **kwargs: mock_llm

        llm = create_groq_llm()
        cfg = AgentConfig(llm=llm)
        crew = build_crew(cfg)

        # Mock crew.kickoff to raise an exception
        with patch("crewai.crew.Crew.kickoff", side_effect=Exception("Agent error")):
            enhanced = _enhance_mood_with_agents("test mood", intense=False, soft=False, crew=crew)

        assert enhanced is None


def test_enhance_mood_with_agents_invalid_output(monkeypatch) -> None:
    """Test mood enhancement when agents return invalid output."""
    monkeypatch.setenv("GROQ_API_KEY", "test-key")

    with patch("simrai.agents.ChatGroq") as mock_groq, patch(
        "crewai.utilities.llm_utils.create_llm"
    ) as mock_create_llm, patch("crewai.llm.LLM.__new__") as mock_llm_new:
        mock_llm = _create_mock_llm()
        mock_groq.return_value = mock_llm
        mock_create_llm.side_effect = lambda llm: llm
        mock_llm_new.side_effect = lambda cls, *args, **kwargs: mock_llm

        llm = create_groq_llm()
        cfg = AgentConfig(llm=llm)
        crew = build_crew(cfg)

        # Mock crew.kickoff to return invalid JSON
        mock_result = MagicMock()
        mock_result.__str__ = lambda x: "Invalid output"
        with patch("crewai.crew.Crew.kickoff", return_value=mock_result):
            enhanced = _enhance_mood_with_agents("test mood", intense=False, soft=False, crew=crew)

        assert enhanced is None


def test_run_with_agents_success(monkeypatch) -> None:
    """Test running pipeline with agents when available."""
    monkeypatch.setenv("GROQ_API_KEY", "test-key")

    with patch("simrai.agents.ChatGroq") as mock_groq, patch(
        "simrai.agents.is_ai_available", return_value=True
    ), patch("simrai.pipeline.is_ai_available", return_value=True), patch(
        "crewai.utilities.llm_utils.create_llm"
    ) as mock_create_llm, patch("crewai.llm.LLM.__new__") as mock_llm_new:
        mock_llm = _create_mock_llm()
        mock_groq.return_value = mock_llm
        mock_create_llm.side_effect = lambda llm: llm
        mock_llm_new.side_effect = lambda cls, *args, **kwargs: mock_llm

        llm = create_groq_llm()
        cfg = AgentConfig(llm=llm)
        crew = build_crew(cfg)

        # Mock successful enhancement
        mock_enhanced = MoodInterpretation(
            vector=MoodVector(valence=0.7, energy=0.6),
            search_terms=["enhanced", "mood"],
        )
        with patch("simrai.agents._enhance_mood_with_agents", return_value=mock_enhanced):
            # Mock generate_queue to avoid real Spotify calls
            with patch("simrai.pipeline.generate_queue") as mock_generate:
                mock_result = MagicMock()
                mock_result.summary = "Test summary"
                mock_generate.return_value = mock_result

                result = run_with_agents("test mood", length=10, crew=crew)

                assert result is not None


def test_run_with_agents_fallback_to_rule_based(monkeypatch) -> None:
    """Test that pipeline falls back to rule-based when agents fail."""
    monkeypatch.setenv("GROQ_API_KEY", "test-key")

    with patch("simrai.agents.ChatGroq") as mock_groq, patch(
        "crewai.utilities.llm_utils.create_llm"
    ) as mock_create_llm, patch("crewai.llm.LLM.__new__") as mock_llm_new:
        mock_llm = _create_mock_llm()
        mock_groq.return_value = mock_llm
        mock_create_llm.side_effect = lambda llm: llm
        mock_llm_new.side_effect = lambda cls, *args, **kwargs: mock_llm

        llm = create_groq_llm()
        cfg = AgentConfig(llm=llm)
        crew = build_crew(cfg)

        # Mock failed enhancement - patch both the enhancement and generate_queue
        with patch("simrai.agents._enhance_mood_with_agents", return_value=None), patch(
            "simrai.agents.generate_queue"
        ) as mock_generate:
            mock_result = MagicMock()
            mock_result.tracks = []
            mock_result.mood_text = "test mood"
            mock_result.mood_vector = MoodVector(valence=0.5, energy=0.5)
            mock_result.summary = "Test"
            mock_generate.return_value = mock_result

            result = run_with_agents("test mood", length=10, crew=crew)

            assert result is not None
            mock_generate.assert_called_once()


def test_generate_queue_tries_ai_first(monkeypatch) -> None:
    """Test that generate_queue attempts AI enhancement first."""
    monkeypatch.setenv("GROQ_API_KEY", "test-key")

    # Patch is_ai_available to return True, and patch all the agent functions to avoid exceptions
    # This simulates the AI path being taken successfully
    # Note: generate_queue imports these inside a try block, so we patch them before calling
    mock_result = QueueResult(
        mood_text="test mood",
        mood_vector=MoodVector(valence=0.5, energy=0.5),
        tracks=[],
        summary="AI-enhanced queue",
    )
    
    # Patch where generate_queue will import them from (it imports from simrai.agents)
    with patch("simrai.agents.is_ai_available", return_value=True), patch(
        "simrai.agents.create_groq_llm"
    ) as mock_create, patch("simrai.agents.build_crew") as mock_build_crew, patch(
        "simrai.agents.AgentConfig"
    ) as mock_config, patch(
        "simrai.agents.run_with_agents", return_value=mock_result
    ) as mock_run_agents:
        mock_llm = _create_mock_llm()
        mock_create.return_value = mock_llm
        mock_crew = MagicMock()
        mock_build_crew.return_value = mock_crew
        # Make AgentConfig work
        mock_cfg_instance = MagicMock()
        mock_cfg_instance.llm = mock_llm
        mock_config.return_value = mock_cfg_instance
        
        result = generate_queue("test mood", length=10)

        # Should have attempted AI and returned the AI-enhanced result
        assert result is not None
        assert result.summary == "AI-enhanced queue"
        # Verify run_with_agents was called (it's imported inside generate_queue's try block)
        mock_run_agents.assert_called_once()


def test_generate_queue_falls_back_when_ai_unavailable(monkeypatch) -> None:
    """Test that generate_queue falls back to rule-based when AI is unavailable."""
    with patch("simrai.pipeline.is_ai_available", return_value=False), patch(
        "simrai.pipeline.SpotifyService"
    ) as mock_service:
        mock_service_instance = MagicMock()
        mock_service.return_value = mock_service_instance
        mock_service_instance.search_tracks.return_value = []
        mock_service_instance.close.return_value = None

        # Should use rule-based interpret_mood
        with patch("simrai.pipeline.interpret_mood") as mock_interpret:
            mock_interpret.return_value = MoodInterpretation(
                vector=MoodVector(valence=0.5, energy=0.5),
                search_terms=["test"],
            )

            result = generate_queue("test mood", length=10)

            # Should have used rule-based interpretation
            mock_interpret.assert_called_once()
            assert result is not None


def test_generate_queue_falls_back_on_ai_error(monkeypatch) -> None:
    """Test that generate_queue falls back when AI raises an error."""
    monkeypatch.setenv("GROQ_API_KEY", "test-key")

    with patch("simrai.pipeline.is_ai_available", return_value=True), patch(
        "simrai.agents.create_groq_llm", side_effect=Exception("AI error")
    ), patch("simrai.pipeline.SpotifyService") as mock_service:
        mock_service_instance = MagicMock()
        mock_service.return_value = mock_service_instance
        mock_service_instance.search_tracks.return_value = []
        mock_service_instance.close.return_value = None

        with patch("simrai.pipeline.interpret_mood") as mock_interpret:
            mock_interpret.return_value = MoodInterpretation(
                vector=MoodVector(valence=0.5, energy=0.5),
                search_terms=["test"],
            )

            result = generate_queue("test mood", length=10)

            # Should have fallen back to rule-based
            mock_interpret.assert_called_once()
            assert result is not None

