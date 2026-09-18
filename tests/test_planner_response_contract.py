"""Synthetic reproductions of the live planner's ambiguous coverage rejection."""

import pytest
from pydantic import ValidationError

from agents.v2_coverage import claim_component_focus
from models import V2ClaimCoverageFocus, V2ClaimCoverageKind, V2InitialPlannerModelOutput
from providers.mimo import _schema_diagnostics


def test_planner_omitted_kind_has_valid_application_owned_default() -> None:
    output = V2InitialPlannerModelOutput.model_validate(
        {
            "searches": [],
            "claim_coverage_focus": [
                {"dimension": "population_and_setting", "claim_component": "adolescents"}
            ],
        }
    )
    assert output.claim_coverage_focus[0].kind is V2ClaimCoverageKind.CLAIM_COMPONENT
    assert output.claim_coverage_focus[0].searchable
    focus = claim_component_focus("Sleep improves in adolescents", output.claim_coverage_focus)
    assert len(focus) == 2
    assert focus[0].claim_component == "Sleep improves in adolescents"
    assert focus[1].claim_component == "adolescents"
    # The generic historical model must retain its old optional-kind semantics.
    historical = V2ClaimCoverageFocus(
        dimension="population_and_setting", claim_component="adolescents"
    )
    assert historical.kind is None


@pytest.mark.parametrize(
    "override",
    [
        {"dimension": "limitations_and_boundaries", "kind": "evidence_audit"},
        {"kind": None},
        {"searchable": False, "unavailable_reason": "Unknown"},
    ],
)
def test_planner_still_rejects_non_claim_components(override: dict[str, object]) -> None:
    component = {
        "dimension": "population_and_setting",
        "claim_component": "adolescents",
        "kind": "claim_component",
    }
    with pytest.raises(ValidationError):
        V2InitialPlannerModelOutput.model_validate(
            {"searches": [], "claim_coverage_focus": [component | override]}
        )


def test_planner_duplicate_dimensions_have_safe_specific_diagnostic() -> None:
    component = {
        "dimension": "population_and_setting",
        "claim_component": "private-input-must-not-appear",
        "kind": "claim_component",
    }
    with pytest.raises(ValidationError) as failure:
        V2InitialPlannerModelOutput.model_validate(
            {"searches": [], "claim_coverage_focus": [component, component]}
        )
    assert _schema_diagnostics(failure.value) == (
        "claim_coverage_focus:planner_duplicate_coverage_dimension"
    )


def test_planner_schema_only_advertises_permitted_claim_dimensions() -> None:
    schema = V2InitialPlannerModelOutput.model_json_schema()
    reference = schema["properties"]["claim_coverage_focus"]["items"]["$ref"].split("/")[-1]
    properties = schema["$defs"][reference]["properties"]
    assert set(properties["dimension"]["enum"]) == {
        "effect_or_association",
        "population_and_setting",
        "mechanism_or_pathway",
    }
    assert properties["kind"]["const"] == "claim_component"
    assert properties["searchable"]["const"] is True
