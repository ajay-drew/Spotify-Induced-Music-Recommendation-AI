"""
Basic tests for the SIMRAI CLI entrypoint.

These tests focus on:
- Ensuring the Typer app is wired correctly
- Verifying that the `queue` command can run end-to-end when the
  underlying `generate_queue` function is patched, so no real Spotify
  calls are made during tests.
"""

from __future__ import annotations

from typer.testing import CliRunner
from unittest.mock import patch

from simrai.cli import app
from simrai.mood import MoodVector
from simrai.pipeline import QueueResult, QueueTrack


def _fake_queue(
    mood_text: str,
    *,
    length: int = 12,
    intense: bool = False,
    soft: bool = False,
) -> QueueResult:  # noqa: ARG001
    """Return a simple, deterministic fake queue for CLI tests."""
    track = QueueTrack(
        name="Test Track",
        artists="Test Artist",
        uri="spotify:track:dummy",
        valence=0.6,
        energy=0.4,
    )
    return QueueResult(
        mood_text=mood_text,
        mood_vector=MoodVector(valence=0.5, energy=0.5),
        tracks=[track],
        summary="Test summary for CLI.",
    )


def test_cli_queue_command_smoke() -> None:
    """
    The `queue` command should run successfully and render the table output
    when `generate_queue` returns a valid QueueResult.
    """
    runner = CliRunner()

    with patch("simrai.cli.generate_queue", _fake_queue):
        result = runner.invoke(app, ["queue", "happy mood", "--length", "8"])

    assert result.exit_code == 0
    # Basic sanity checks on output
    assert "SIMRAI Queue" in result.stdout
    assert "Test Track" in result.stdout
    assert "Test Artist" in result.stdout


