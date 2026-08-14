from __future__ import annotations

from uuid import uuid4

import pytest
from pydantic import ValidationError

from agents.planner import PlannerLLMInput
from models import (
    DEFAULT_RESEARCH_CONTROLS,
    PresentationTone,
    ReportLength,
    ResearchControls,
    ResearchDepth,
    ResearchFocus,
)


def test_research_controls_have_safe_defaults() -> None:
    assert DEFAULT_RESEARCH_CONTROLS == ResearchControls()
    assert DEFAULT_RESEARCH_CONTROLS.depth is ResearchDepth.STANDARD
    assert DEFAULT_RESEARCH_CONTROLS.length is ReportLength.REPORT
    assert DEFAULT_RESEARCH_CONTROLS.tone is PresentationTone.NEUTRAL
    assert DEFAULT_RESEARCH_CONTROLS.focus is None


def test_persisted_controls_allow_later_policy_identity_segments() -> None:
    controls = ResearchControls(
        depth=ResearchDepth.FOCUSED,
        length=ReportLength.BRIEF,
        tone=PresentationTone.EXECUTIVE,
    )

    restored = ResearchControls.from_policy_identity(
        f"mvp9-policy|controls:{controls.canonical_json()}|mvp11-research-governor-v1"
    )

    assert restored == controls


def test_valid_controls_are_frozen_and_reach_planner_input() -> None:
    controls = ResearchControls(
        depth=ResearchDepth.FOCUSED,
        length=ReportLength.BRIEF,
        tone=PresentationTone.PLAIN_LANGUAGE,
        focus=ResearchFocus(geographic_area="California", timeframe="2020-2024"),
    )
    planner_input = PlannerLLMInput(
        run_id=uuid4(), raw_claim="A public claim", research_controls=controls
    )
    assert planner_input.research_controls == controls
    assert '"tone":"plain_language"' in controls.canonical_json()
    with pytest.raises(ValidationError):
        controls.tone = PresentationTone.ACADEMIC  # type: ignore[misc]


@pytest.mark.parametrize(
    "payload",
    [
        {"depth": "unknown"},
        {"tone": "casual"},
        {"focus": {}},
        {"focus": {"population": " people "}},
        {"unknown": "value"},
    ],
)
def test_invalid_controls_fail_closed(payload: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        ResearchControls.model_validate(payload)


def test_tone_is_isolated_from_explicit_focus_and_factual_planner_claim() -> None:
    claim = "A public claim remains exact."
    controls = ResearchControls(tone=PresentationTone.EXECUTIVE)
    planner_input = PlannerLLMInput(run_id=uuid4(), raw_claim=claim, research_controls=controls)
    assert planner_input.raw_claim == claim
    assert planner_input.research_controls.focus is None
