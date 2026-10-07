from __future__ import annotations

from uuid import uuid4

import pytest

from researchassistant.contracts.discovery_v2 import (
    V2ConceptGroup,
    V2ConceptualQuery,
    V2DiscoveryPolicy,
    discovery_id,
)
from researchassistant.contracts.model_contracts import DiscoveryProvider
from researchassistant.contracts.research_directions import ResearchDirection
from researchassistant.research.query_compiler import compile_query, conceptual_signature


def _query(
    provider: DiscoveryProvider,
    concepts: tuple[tuple[str, tuple[str, ...]], ...],
    *,
    purpose: str = "broad",
    methods: tuple[str, ...] = (),
    outcomes: tuple[str, ...] = (),
) -> V2ConceptualQuery:
    run_id = uuid4()
    identity_key = f"query-{uuid4().hex}"
    return V2ConceptualQuery(
        run_id=run_id,
        artifact_id=discovery_id(run_id, "V2ConceptualQuery", identity_key),
        identity_key=identity_key,
        required_concepts=tuple(
            V2ConceptGroup(concept=concept, synonyms=aliases) for concept, aliases in concepts
        ),
        methods=methods,
        outcomes=outcomes,
        purpose=purpose,
        direction=ResearchDirection.SUPPORT,
        provider=provider,
        round_number=1,
        target_gap_ids=("gap-1",) if purpose == "gap" else (),
    )


@pytest.mark.parametrize(
    ("provider", "mode", "concepts", "parameter"),
    [
        (
            DiscoveryProvider.OPENALEX,
            "lexical",
            (("crime prevention", ("violence reduction",)),),
            "search",
        ),
        (
            DiscoveryProvider.OPENALEX,
            "semantic",
            (("crime prevention", ("violence reduction",)),),
            "search.semantic",
        ),
        (
            DiscoveryProvider.ARXIV,
            "lexical",
            (("fairness auditing", ("algorithmic audits",)),),
            "search_query",
        ),
        (DiscoveryProvider.PUBMED, "lexical", (("maternal health", ("pregnancy care",)),), "term"),
        (
            DiscoveryProvider.EXA,
            "provider_default",
            (("school discipline", ("student punishment",)),),
            "query",
        ),
        (
            DiscoveryProvider.SERPSEARCH,
            "lexical",
            (("housing discrimination", ("rental bias",)),),
            "query",
        ),
    ],
)
def test_compiles_supported_provider_modes_to_application_owned_parameters(
    provider: DiscoveryProvider,
    mode: str,
    concepts: tuple[tuple[str, tuple[str, ...]], ...],
    parameter: str,
) -> None:
    action = compile_query(_query(provider, concepts), mode=mode)

    assert action.mode == mode
    assert action.effective_depth == 5
    assert {item.name for item in action.parameters} >= {parameter}
    assert action.query_text
    assert action.capabilities.provider == provider


def test_semantic_openalex_mode_has_a_bounded_depth_and_distinct_parameter() -> None:
    action = compile_query(
        _query(DiscoveryProvider.OPENALEX, (("crime prevention", ()),)),
        mode="semantic",
        requested_depth=50,
        policy=V2DiscoveryPolicy(metadata_depth=50),
    )

    assert action.effective_depth == 50
    assert (
        dict((item.name, item.value) for item in action.parameters)["search.semantic"]
        == action.query_text
    )


@pytest.mark.parametrize(
    ("provider", "mode", "purpose", "methods", "outcomes", "expected"),
    [
        (
            DiscoveryProvider.EXA,
            "provider_default",
            "gap",
            ("randomized trial",),
            ("student attendance",),
            "method or outcome evidence involving randomized trial or student attendance",
        ),
        (
            DiscoveryProvider.OPENALEX,
            "semantic",
            "outcomes",
            (),
            ("mortality", "attendance"),
            "outcome evidence involving mortality or attendance",
        ),
    ],
)
def test_natural_language_modes_preserve_method_and_outcome_roles(
    provider: DiscoveryProvider,
    mode: str,
    purpose: str,
    methods: tuple[str, ...],
    outcomes: tuple[str, ...],
    expected: str,
) -> None:
    action = compile_query(
        _query(
            provider,
            (("school attendance boundaries", ()),),
            purpose=purpose,
            methods=methods,
            outcomes=outcomes,
        ),
        mode=mode,
    )

    assert expected in action.query_text
    assert "also called" not in action.query_text


def test_unicode_phrase_punctuation_is_normalized_and_quoted_as_data() -> None:
    action = compile_query(_query(DiscoveryProvider.PUBMED, (("children’s health—equity", ()),)))

    assert '"children’s health—equity"[tiab]' in action.query_text


@pytest.mark.parametrize(
    "term",
    [
        '"crime" OR prevention',
        "prevention) OR (all:fraud",
        "AND",
        "crime\u202e prevention",
        "x" * 181,
    ],
)
def test_rejects_executable_or_unbounded_concept_text(term: str) -> None:
    query = _query(DiscoveryProvider.ARXIV, ((term, ()),))

    with pytest.raises(ValueError):
        compile_query(query)


def test_rejects_unsupported_provider_mode_before_query_creation() -> None:
    query = _query(DiscoveryProvider.PUBMED, (("maternal health", ()),))

    with pytest.raises(ValueError, match="unsupported search mode"):
        compile_query(query, mode="semantic")
    with pytest.raises(ValueError, match="unsupported search mode"):
        compile_query(query, mode="")


def test_material_signature_ignores_alias_order_but_keeps_substantive_changes() -> None:
    first = _query(
        DiscoveryProvider.OPENALEX,
        (("crime prevention", ("violence reduction", "public safety")),),
    )
    reordered = _query(
        DiscoveryProvider.OPENALEX,
        (("crime prevention", ("public safety", "violence reduction")),),
    )
    changed = _query(
        DiscoveryProvider.OPENALEX,
        (("crime prevention", ("victim services",)),),
    )

    assert conceptual_signature(first, "lexical") == conceptual_signature(reordered, "lexical")
    assert conceptual_signature(first, "lexical") != conceptual_signature(changed, "lexical")
