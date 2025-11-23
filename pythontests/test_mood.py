import pytest

from simrai.mood import MoodInterpretation, interpret_mood
import simrai.mood as mood_mod


@pytest.fixture(autouse=True)
def disable_groq_in_tests(monkeypatch) -> None:
    """
    Ensure Groq/LLM calls are disabled for most tests so they remain
    deterministic even when GROQ_API_KEY is set in the environment.
    """
    monkeypatch.setattr(mood_mod, "_call_groq_mood_ai", lambda *a, **k: None)


@pytest.mark.parametrize(
    "text,intense,soft,expected_valence_range,expected_energy_range",
    [
        ("neutral evening", False, False, (0.45, 0.55), (0.45, 0.55)),
        ("sad lonely night", False, False, (0.0, 0.4), (0.2, 0.6)),
        ("happy party", False, False, (0.6, 1.0), (0.5, 1.0)),
        ("chill sleepy midnight", False, False, (0.3, 0.7), (0.0, 0.4)),
        ("rage workout", True, False, (0.5, 1.0), (0.7, 1.0)),
        ("soft piano night", False, True, (0.2, 0.6), (0.0, 0.4)),
    ],
)
def test_interpret_mood_valence_energy_ranges(
    text, intense, soft, expected_valence_range, expected_energy_range
) -> None:
    interp: MoodInterpretation = interpret_mood(text, intense=intense, soft=soft)
    v = interp.vector.valence
    e = interp.vector.energy
    lo_v, hi_v = expected_valence_range
    lo_e, hi_e = expected_energy_range
    assert lo_v <= v <= hi_v
    assert lo_e <= e <= hi_e


def test_interpret_mood_metadata_preferences() -> None:
    text = "underground obscure deep classic 90s hits new 2024"
    interp = interpret_mood(text)

    # All preference flags should be derivable from the wording.
    assert interp.prefer_obscure is True
    assert interp.prefer_popular is True
    assert interp.prefer_recent is True
    assert interp.prefer_classics is True


def test_interpret_mood_search_terms_include_flags() -> None:
    text = "late night drive"
    interp_soft = interpret_mood(text, soft=True)
    interp_intense = interpret_mood(text, intense=True)

    assert text in interp_soft.search_terms
    assert "acoustic" in interp_soft.search_terms
    assert "chill" in interp_soft.search_terms

    assert text in interp_intense.search_terms
    assert "intense" in interp_intense.search_terms


def test_interpret_mood_uses_ai_data_when_available(monkeypatch) -> None:
    """
    When the Groq helper returns data, interpret_mood should merge it into
    the base interpretation (valence/energy, preferences, and extra terms).
    """

    def fake_ai(text: str, *, intense: bool, soft: bool):  # noqa: ARG001
        return {
            "valence": 0.9,
            "energy": 0.1,
            "search_terms": ["deep focus", "late night study"],
            "prefer_popular": False,
            "prefer_obscure": True,
            "prefer_recent": False,
            "prefer_classics": True,
        }

    # Re-enable AI path just for this test.
    monkeypatch.setattr(mood_mod, "_call_groq_mood_ai", fake_ai)

    interp = interpret_mood("some mood text", intense=False, soft=False)

    assert interp.vector.valence == pytest.approx(0.9)
    assert interp.vector.energy == pytest.approx(0.1)
    assert interp.prefer_obscure is True
    assert interp.prefer_classics is True

    # Base text should still be present, plus AI-suggested terms.
    assert "some mood text" in interp.search_terms
    assert any("deep focus" in s for s in interp.search_terms)
    assert any("late night study" in s for s in interp.search_terms)

