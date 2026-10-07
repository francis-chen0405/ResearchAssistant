"""Acceptance tests for the immutable, opt-in source discovery contract surface."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from hashlib import sha256
from typing import Any
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from providers.v2_routing import V2RoutingConfig
from researchassistant.contracts.discovery_v2 import (
    V2CompiledQueryAction,
    V2ConceptGroup,
    V2ConceptualQuery,
    V2DiscoveryBinding,
    V2DiscoveryClientSettings,
    V2DiscoveryPolicy,
    V2DiscoveryProviderBudget,
    V2GraphNeighborAction,
    V2IdentityLookupAction,
    V2PreviewRequest,
    V2PreviewResult,
    V2PreviewSpan,
    V2ProviderCapabilities,
    V2RankComponents,
    V2RawDiscoveryCandidate,
    V2SeedEligibility,
    V2SourceLocation,
    V2WorkIdentity,
    discovery_id,
)
from researchassistant.contracts.model_contracts import DiscoveryProvider, SourceSnapshot
from researchassistant.contracts.model_research import ResearchDirection, ResearchDirections
from researchassistant.research.v2_orchestrator import V2RunCeilings, _production_fingerprint


def artifact(cls: type[Any], run_id: UUID, key: str, **fields: Any) -> Any:
    """Build a correctly namespaced artifact for a given test scenario."""
    return cls(
        run_id=run_id,
        artifact_id=discovery_id(run_id, cls.__name__, key),
        identity_key=key,
        **fields,
    )


def capabilities(
    provider: DiscoveryProvider = DiscoveryProvider.OPENALEX,
    **overrides: Any,
) -> V2ProviderCapabilities:
    """Return a small plausible provider capability description."""
    fields: dict[str, Any] = {
        "provider": provider,
        "search_modes": ("lexical", "semantic"),
        "fields": ("title", "abstract"),
        "operators": ("AND",),
        "max_metadata_per_page": 10,
        "max_metadata_per_operation": 30,
        "pagination": "page",
        "identity_lookup": True,
        "relationships": ("references",),
        "executable_search_modes": ("lexical",),
        "executable_relationships": (),
        "unsupported_features": ("full_text_search",),
        "documentation_urls": ("https://api.openalex.org/about",),
        "restrictions": ("public metadata only",),
    }
    fields.update(overrides)
    return V2ProviderCapabilities(**fields)


def concept_query(run_id: UUID) -> V2ConceptualQuery:
    """Return a valid conceptual query used by compiled-action scenarios."""
    return artifact(
        V2ConceptualQuery,
        run_id,
        "concept-query",
        required_concepts=(V2ConceptGroup(concept="school attendance"),),
        purpose="broad",
        direction=ResearchDirection.SUPPORT,
        provider=DiscoveryProvider.OPENALEX,
        round_number=1,
    )


def test_contract_json_round_trip_is_strict_frozen_and_stable() -> None:
    """Persisted contracts decode identically and reject mutation or future fields."""
    query = concept_query(uuid4())
    encoded = query.model_dump_json()
    decoded = V2ConceptualQuery.model_validate_json(encoded)

    assert decoded == query
    assert decoded.model_dump(mode="json") == query.model_dump(mode="json")
    with pytest.raises(ValidationError):
        V2ConceptualQuery.model_validate_json(encoded[:-1] + ',"unexpected":true}')
    with pytest.raises(ValidationError):
        query.purpose = "gap"  # type: ignore[misc]


@pytest.mark.parametrize(
    "values",
    [
        {"metadata_depth": 0},
        {"metadata_depth": 51},
        {"max_pages_per_operation": 4},
        {"max_raw_per_round": 301},
        {"max_neighbors_per_seed": 11},
        {"max_acquisition_per_round": 61},
        {"max_acquisition_per_round": 20, "max_scout_per_round": 10},
        {"max_neighbors_per_seed": 9, "max_expansion_per_run": 8},
    ],
)
def test_policy_rejects_values_outside_operational_bounds(values: dict[str, int]) -> None:
    """Policy values stay within the published ceilings and remain coherent."""
    with pytest.raises(ValidationError):
        V2DiscoveryPolicy(**values)


def test_artifact_identity_cannot_be_forged_or_reused_across_runs() -> None:
    """Application artifact IDs are derived from both run and artifact family."""
    run_id = uuid4()
    values = {
        "run_id": run_id,
        "artifact_id": uuid4(),
        "identity_key": "concept-query",
        "required_concepts": (V2ConceptGroup(concept="attendance"),),
        "purpose": "broad",
        "direction": ResearchDirection.SUPPORT,
        "provider": DiscoveryProvider.OPENALEX,
        "round_number": 1,
    }
    with pytest.raises(ValidationError, match="application-owned"):
        V2ConceptualQuery(**values)
    query = concept_query(run_id)
    wrong_run = query.model_dump(mode="python")
    wrong_run["run_id"] = uuid4()
    with pytest.raises(ValidationError, match="application-owned"):
        V2ConceptualQuery(**wrong_run)


def test_enabled_direction_and_concept_synonym_contracts_are_enforced() -> None:
    """At least one research lane is enabled and concepts stay compact and distinct."""
    with pytest.raises(ValidationError):
        ResearchDirections(support_enabled=False, challenge_enabled=False)
    query_values = concept_query(uuid4()).model_dump(mode="python")
    query_values["direction"] = ResearchDirection.CHALLENGE
    query_values["directions"] = ResearchDirections(support_enabled=True, challenge_enabled=False)
    with pytest.raises(ValidationError):
        V2PreviewRequest(**query_values)
    assert V2ConceptGroup(concept="attendance").synonyms == ()
    assert len(V2ConceptGroup(concept="attendance", synonyms=("presence",) * 1).synonyms) == 1
    with pytest.raises(ValidationError):
        V2ConceptGroup(concept="attendance", synonyms=("Presence", "presence"))
    with pytest.raises(ValidationError):
        V2ConceptGroup(concept="attendance", synonyms=tuple(f"term-{i}" for i in range(6)))


@pytest.mark.parametrize("doi", ("not-a-doi", "10.123/short", "10.1234/"))
def test_verified_doi_identity_rejects_malformed_identifiers(doi: str) -> None:
    with pytest.raises(ValidationError, match="DOI identifier is malformed"):
        V2WorkIdentity(
            grouping_key="untrusted-grouping-key",
            doi=doi,
            resolution="verified_identifiers",
        )


@pytest.mark.parametrize(
    ("doi", "expected"),
    [
        ("10.1234/AbC:def", "10.1234/abc:def"),
        ("doi:10.1234/AbC:def", "10.1234/abc:def"),
        ("https://doi.org/10.1234/AbC:def", "10.1234/abc:def"),
        ("http://dx.doi.org/10.1234/AbC:def", "10.1234/abc:def"),
    ],
)
def test_verified_doi_identity_normalizes_supported_forms(doi: str, expected: str) -> None:
    identity = V2WorkIdentity(
        grouping_key="doi:10.1234/abc:def", doi=doi, resolution="verified_identifiers"
    )
    assert identity.doi == expected


@pytest.mark.parametrize(
    "url",
    [
        "https://user:password@example.org/article",
        "https://example.org/article?api_key=secret",
        "https://example.org/article?signature=abc",
        "file:///tmp/article.pdf",
    ],
)
def test_source_locations_refuse_embedded_credentials_and_non_web_urls(url: str) -> None:
    """Locations remain safe to persist and display without credential leakage."""
    with pytest.raises(ValidationError):
        V2SourceLocation(url=url)


def test_source_locations_reject_credential_fragments_but_keep_plain_anchors() -> None:
    """Credential-bearing fragments are sensitive while normal section links are safe."""
    with pytest.raises(ValidationError):
        V2SourceLocation(url="https://example.org/article#access_token=secret")
    location = V2SourceLocation(url="https://example.org/article#methods")
    assert location.url.endswith("#methods")


def test_capabilities_separate_documented_support_from_executable_modes_and_depth() -> None:
    """A listed capability does not authorize a mode that is not executable natively."""
    run_id = uuid4()
    query = concept_query(run_id)
    caps = capabilities()
    base: dict[str, Any] = {
        "conceptual_query": query,
        "query_text": "attendance",
        "mode": "semantic",
        "requested_depth": 25,
        "effective_depth": 10,
        "policy": V2DiscoveryPolicy(metadata_depth=25),
        "capabilities": caps,
        "fingerprint": "0" * 64,
    }
    with pytest.raises(ValidationError, match="unsupported search mode"):
        artifact(V2CompiledQueryAction, run_id, "compiled", **base)
    semantic_caps = capabilities(executable_search_modes=("lexical", "semantic"))
    with pytest.raises(ValidationError, match="fingerprint|effective metadata depth"):
        action_payload = dict(base, capabilities=semantic_caps, effective_depth=31)
        artifact(V2CompiledQueryAction, run_id, "compiled", **action_payload)


def test_compiled_query_rejects_stale_fingerprint_even_when_shape_is_valid() -> None:
    """The fingerprint binds the exact query payload, including requested depth."""
    run_id = uuid4()
    query = concept_query(run_id)
    values: dict[str, Any] = {
        "conceptual_query": query.model_dump(mode="json"),
        "query_text": "school attendance",
        "mode": "lexical",
        "requested_depth": 8,
        "effective_depth": 8,
        "policy": V2DiscoveryPolicy().model_dump(mode="json"),
        "capabilities": capabilities().model_dump(mode="json"),
        "fingerprint": "0" * 64,
    }
    with pytest.raises(ValidationError, match="fingerprint"):
        artifact(V2CompiledQueryAction, run_id, "compiled", **values)


def test_normalization_cannot_merge_cross_run_or_different_work_records() -> None:
    """A normalized record retains run ownership and one stable work grouping."""
    run_id = uuid4()
    raw = artifact(
        V2RawDiscoveryCandidate,
        run_id,
        "raw-one",
        operation_id=uuid4(),
        attempt_id=uuid4(),
        provider=DiscoveryProvider.OPENALEX,
        direction=ResearchDirection.SUPPORT,
        round_number=1,
        provider_rank=1,
        response_hash="a" * 64,
        work=V2WorkIdentity(
            grouping_key="doi:10.1234/a", doi="doi:10.1234/a", resolution="verified_identifiers"
        ),
    )
    from researchassistant.contracts.discovery_v2 import V2NormalizedDiscoveryCandidate

    common: dict[str, Any] = {
        "raw_candidates": (raw,),
        "work": raw.work,
        "rank": V2RankComponents(rationale="Matches the declared topic"),
        "disposition": "retained",
        "disposition_reason": "First unique work in the operation",
    }
    changed = dict(
        common,
        work=V2WorkIdentity(
            grouping_key="doi:10.1234/b", doi="doi:10.1234/b", resolution="verified_identifiers"
        ),
    )
    with pytest.raises(ValidationError, match="grouping"):
        artifact(V2NormalizedDiscoveryCandidate, run_id, "normalized", **changed)
    foreign_run = uuid4()
    foreign_raw = raw.model_copy(
        update={
            "run_id": foreign_run,
            "artifact_id": discovery_id(foreign_run, type(raw).__name__, raw.identity_key),
        }
    )
    with pytest.raises(ValidationError, match="cross-run"):
        artifact(
            V2NormalizedDiscoveryCandidate,
            run_id,
            "normalized",
            **dict(common, raw_candidates=(foreign_raw,)),
        )


def test_preview_checks_actual_snapshot_identity_hash_exact_offsets_and_context() -> None:
    """Preview spans must point into the immutable source snapshot they name."""
    run_id = uuid4()
    source_id = uuid4()
    snapshot_id = uuid4()
    body = "Method details. Results show a small change. Discussion follows."
    body_hash = sha256(body.encode()).hexdigest()
    snapshot = SourceSnapshot(
        run_id=run_id,
        retrieval_attempt_id=uuid4(),
        snapshot_id=snapshot_id,
        source_url="https://example.org/paper",
        retrieved_at=datetime.now(UTC),
        normalized_text=body,
        snapshot_sha256=body_hash,
        word_count=len(body.split()),
        truncated=False,
        created_at=datetime.now(UTC),
    )
    request = artifact(
        V2PreviewRequest,
        run_id,
        "preview-request",
        exact_claim="The program improves attendance.",
        direction=ResearchDirection.SUPPORT,
        directions=ResearchDirections(support_enabled=True, challenge_enabled=False),
        source_id=source_id,
        snapshot_id=snapshot_id,
        snapshot_hash=body_hash,
    )
    start = body.index("Results")
    span = V2PreviewSpan(
        start=start,
        end=start + len("Results show a small change."),
        text="Results show a small change.",
        section="results",
        context_before=body[:start],
        context_after=body[start + len("Results show a small change.") :],
    )
    result = artifact(
        V2PreviewResult,
        run_id,
        "preview-result",
        request=request,
        spans=(span,),
        content_classification="full_text",
        outcome="completed",
        reason="An exact results passage was found",
    )
    with pytest.raises(ValidationError):
        V2PreviewSpan(start=4, end=4, text="x", section="results")
    result.require_snapshot(snapshot)
    forged_context = result.model_copy(
        update={"spans": (span.model_copy(update={"context_before": "different"}),)}
    )
    with pytest.raises(ValueError):
        forged_context.require_snapshot(snapshot)
    wrong_owner = snapshot.model_copy(update={"run_id": uuid4()})
    with pytest.raises(ValueError):
        result.require_snapshot(wrong_owner)


def test_seed_and_one_hop_expansion_reject_unresolved_self_cycle_and_bad_provenance() -> None:
    """Only a usable resolved seed can expand to distinct same-operation neighbors."""
    run_id = uuid4()
    identity = V2WorkIdentity(
        grouping_key="doi:10.1234/seed", doi="10.1234/seed", resolution="verified_identifiers"
    )
    invalid: dict[str, Any] = {
        "candidate_id": uuid4(),
        "work": V2WorkIdentity(grouping_key="unknown", resolution="unresolved"),
        "eligible": True,
        "reason": "Has an abstract but is unresolved",
    }
    with pytest.raises(ValidationError, match="eligible seed"):
        artifact(V2SeedEligibility, run_id, "seed", **invalid)
    seed = artifact(
        V2SeedEligibility,
        run_id,
        "seed",
        candidate_id=uuid4(),
        source_id=uuid4(),
        snapshot_id=uuid4(),
        work=identity,
        eligible=True,
        reason="Resolved work has a usable immutable snapshot",
    )
    action = artifact(
        V2GraphNeighborAction,
        run_id,
        "neighbors",
        seed=seed,
        relationship="references",
        provider=DiscoveryProvider.OPENALEX,
        direction=ResearchDirection.SUPPORT,
        round_number=1,
        requested_depth=3,
        policy=V2DiscoveryPolicy(),
        capabilities=capabilities(
            relationships=("references",), executable_relationships=("references",)
        ),
    )
    common: dict[str, Any] = {
        "operation_id": action.artifact_id,
        "attempt_id": uuid4(),
        "provider": action.provider,
        "direction": action.direction,
        "round_number": action.round_number,
        "provider_rank": 1,
        "response_hash": "b" * 64,
    }
    with pytest.raises(ValidationError, match="self cycle"):
        from researchassistant.contracts.discovery_v2 import V2ExpansionEdge

        candidate = artifact(
            V2RawDiscoveryCandidate,
            run_id,
            "raw-self",
            **dict(common, work=identity),
        )
        artifact(
            V2ExpansionEdge,
            run_id,
            "edge-self",
            action=action,
            candidate=candidate,
            edge_verification="provider_reported",
        )
    with pytest.raises(ValidationError, match="provenance"):
        from researchassistant.contracts.discovery_v2 import V2ExpansionEdge

        candidate = artifact(
            V2RawDiscoveryCandidate,
            run_id,
            "raw-neighbor",
            **dict(
                common,
                operation_id=uuid4(),
                work=V2WorkIdentity(
                    grouping_key="doi:10.1234/neighbor",
                    doi="doi:10.1234/neighbor",
                    resolution="verified_identifiers",
                ),
            ),
        )
        artifact(
            V2ExpansionEdge,
            run_id,
            "edge-wrong-operation",
            action=action,
            candidate=candidate,
            edge_verification="provider_reported",
        )


def test_client_policy_settings_distinguish_absent_selected_and_unknown_policy() -> None:
    """Legacy defaults remain identifiable while an explicit new selection is complete."""
    assert V2DiscoveryClientSettings().selected_policy is None
    selected = V2DiscoveryClientSettings(
        selected_policy="source-discovery-v2-2026-10-05-v1", policy=V2DiscoveryPolicy()
    )
    assert selected.policy is not None
    with pytest.raises(ValidationError):
        V2DiscoveryClientSettings(selected_policy="source-discovery-v2-2026-10-05-v1")
    with pytest.raises(ValidationError):
        V2DiscoveryClientSettings.model_validate(
            {"selected_policy": "source-discovery-v3", "policy": {}}
        )


@pytest.mark.parametrize(
    ("provider", "max_requests"),
    [
        (DiscoveryProvider.SERPSEARCH, 13),
        (DiscoveryProvider.EXA, 19),
        (DiscoveryProvider.OPENALEX, 11),
        (DiscoveryProvider.ARXIV, 7),
        (DiscoveryProvider.PUBMED, 7),
    ],
)
def test_provider_budget_cannot_exceed_existing_request_ceiling(
    provider: DiscoveryProvider, max_requests: int
) -> None:
    """Opt-in discovery cannot widen established physical request ceilings."""
    with pytest.raises(ValidationError, match="request ceiling"):
        V2DiscoveryProviderBudget(
            provider=provider,
            max_requests=max_requests,
            max_cost_usd="1.00",
            cost_policy_identity="configured-call-cost-v1",
            reservation_per_request_usd="0.01",
            cost_basis="configured_upper_bound",
        )


def test_provider_budget_requires_known_free_basis_or_positive_reservation() -> None:
    """A missing paid-call estimate cannot be silently recorded as free."""
    with pytest.raises(ValidationError, match="reservation"):
        V2DiscoveryProviderBudget(
            provider=DiscoveryProvider.EXA,
            max_requests=1,
            max_cost_usd="0.00",
            cost_policy_identity="configured-call-cost-v1",
            reservation_per_request_usd="0.00",
            cost_basis="configured_upper_bound",
        )
    with pytest.raises(ValidationError, match="free budget"):
        V2DiscoveryProviderBudget(
            provider=DiscoveryProvider.PUBMED,
            max_requests=1,
            max_cost_usd="0.01",
            cost_policy_identity="documented-free-v1",
            reservation_per_request_usd="0.00",
            cost_basis="documented_free",
        )
    with pytest.raises(ValidationError, match="OpenAlex"):
        V2DiscoveryProviderBudget(
            provider=DiscoveryProvider.OPENALEX,
            max_requests=1,
            max_cost_usd="0.02",
            cost_policy_identity="configured-call-cost-v1",
            reservation_per_request_usd="0.01",
            cost_basis="configured_upper_bound",
        )


def test_unknown_metadata_stays_unknown_and_identity_lookup_requires_native_support() -> None:
    """Incomplete provider records remain unresolved and lookups need declared support."""
    unresolved = V2WorkIdentity(grouping_key="provider-record:unknown", resolution="unresolved")
    assert unresolved.doi is None
    assert unresolved.title is None
    assert unresolved.authors is None
    assert unresolved.publication_year is None
    run_id = uuid4()
    fields: dict[str, Any] = {
        "candidate_id": uuid4(),
        "work_identifier": "provider-record:abc",
        "provider": DiscoveryProvider.OPENALEX,
        "direction": ResearchDirection.SUPPORT,
        "round_number": 1,
        "policy": V2DiscoveryPolicy(),
        "capabilities": capabilities(identity_lookup=False),
    }
    with pytest.raises(ValidationError, match="identity lookup"):
        artifact(V2IdentityLookupAction, run_id, "lookup", **fields)


def test_capability_cannot_mark_identity_lookup_executable_without_native_support() -> None:
    """Execution capability cannot exceed the provider's documented lookup support."""
    with pytest.raises(ValidationError, match="executable lookup"):
        capabilities(identity_lookup=False, executable_identity_lookup=True)


def test_binding_requires_complete_ordered_provider_identity_and_configuration_hashes() -> None:
    """A bound run carries one matching budget and capability record per enabled lane."""
    run_id = uuid4()
    cap = capabilities()
    budget = V2DiscoveryProviderBudget(
        provider=DiscoveryProvider.OPENALEX,
        max_requests=10,
        max_cost_usd="0.01",
        cost_policy_identity="openalex-budget-v1",
        reservation_per_request_usd="0.001",
        cost_basis="configured_upper_bound",
    )
    values: dict[str, Any] = {
        "exact_claim": "Attendance improves after the intervention.",
        "directions": ResearchDirections(support_enabled=True, challenge_enabled=True),
        "providers": (DiscoveryProvider.OPENALEX,),
        "policy": V2DiscoveryPolicy(),
        "capabilities": (cap,),
        "provider_budgets": (budget,),
        "provider_configuration_hash": "a" * 64,
        "source_identity_hash": "b" * 64,
        "prompt_schema_hash": "c" * 64,
    }
    binding = artifact(V2DiscoveryBinding, run_id, "binding", **values)
    assert binding.fingerprint
    with pytest.raises(ValidationError, match="ordered capabilities/budgets"):
        artifact(
            V2DiscoveryBinding,
            run_id,
            "binding-incomplete",
            **dict(values, provider_budgets=()),
        )
    with pytest.raises(ValidationError, match="ordered capabilities/budgets"):
        artifact(
            V2DiscoveryBinding,
            run_id,
            "binding-wrong-provider",
            **dict(
                values,
                providers=(DiscoveryProvider.OPENALEX, DiscoveryProvider.PUBMED),
            ),
        )


def test_existing_production_fingerprint_is_unchanged_by_discovery_metadata_policy() -> None:
    """The new opt-in metadata policy does not alter legacy production identity."""
    routing = V2RoutingConfig.from_environment(
        {
            "MIMO_API_KEY": "test",
            "MIMO_V25_MODEL": "mimo-v2.5",
            "MIMO_V25_INPUT_USD_PER_TOKEN": "0.000001",
            "MIMO_V25_OUTPUT_USD_PER_TOKEN": "0.000002",
            "LUNA_API_KEY": "test",
            "LUNA_BASE_URL": "https://luna.example.test/v1",
            "LUNA_MODEL": "luna",
            "LUNA_INPUT_USD_PER_TOKEN": "0.000003",
            "LUNA_OUTPUT_USD_PER_TOKEN": "0.000004",
        },
        repository_revision="v2-phase12-tests",
    )
    fingerprint = _production_fingerprint(
        UUID("00000000-0000-0000-0000-000000000001"),
        ResearchDirections(support_enabled=True, challenge_enabled=False),
        (DiscoveryProvider.EXA,),
        V2RunCeilings(
            max_physical_calls=40,
            max_total_tokens=100_000,
            max_total_cost_usd=Decimal("1"),
        ),
        routing,
        "test-provider-policy",
        datetime(2026, 1, 1, tzinfo=UTC),
    )

    assert fingerprint.sha256 == "97a0d5eb65a527849dfaf25b3ee99d611568b9c4adf26f46ef6e78e77518754d"
