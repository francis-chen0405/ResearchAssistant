from __future__ import annotations

import pytest
from pydantic import ValidationError

from researchassistant.contracts.query_planning import (
    V2AdaptiveSearchConceptProposal,
    V2AdaptiveSearchConceptsOutput,
    V2InitialPlannerConceptsOutput,
    V2QueryConceptGroup,
    V2QueryConcepts,
)


def test_query_concepts_are_bounded_and_have_no_routing_fields() -> None:
    ingredients = V2QueryConcepts(
        required_concepts=(
            V2QueryConceptGroup(concept="longitudinal study", aliases=("cohort study",)),
        ),
        methods=("randomized trial",),
        outcomes=("clinical outcome",),
        purpose="broad",
    )
    assert V2InitialPlannerConceptsOutput(queries=(ingredients,)).queries == (ingredients,)
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        V2QueryConcepts.model_validate(
            {**ingredients.model_dump(), "provider": "exa", "direction": "support"}
        )


def test_query_concepts_reject_excess_aliases_and_required_concepts() -> None:
    with pytest.raises(ValidationError):
        V2QueryConceptGroup(concept="term", aliases=("a", "b", "c", "d"))
    with pytest.raises(ValidationError):
        V2QueryConcepts(
            required_concepts=tuple(
                V2QueryConceptGroup(concept=f"term {index}") for index in range(9)
            ),
            purpose="broad",
        )


def test_adaptive_query_concepts_require_gap_purpose() -> None:
    ingredients = V2QueryConcepts(
        required_concepts=(V2QueryConceptGroup(concept="replication study"),),
        purpose="gap",
    )
    proposal = V2AdaptiveSearchConceptProposal(lane_index=0, concepts=ingredients)
    assert V2AdaptiveSearchConceptsOutput(searches=(proposal,)).searches == (proposal,)
    with pytest.raises(ValidationError, match="gap purpose"):
        V2AdaptiveSearchConceptsOutput(
            searches=(
                proposal.model_copy(
                    update={"concepts": ingredients.model_copy(update={"purpose": "broad"})}
                ),
            )
        )
