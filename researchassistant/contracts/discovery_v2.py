"""Opt-in discovery foundations; metadata and previews never authorize evidence admission."""

from __future__ import annotations

import json
import re
from datetime import datetime
from decimal import Decimal
from hashlib import sha256
from typing import Annotated, Literal
from urllib.parse import parse_qsl, urlsplit
from uuid import UUID, uuid5

from pydantic import ConfigDict, Field, field_validator, model_validator

from researchassistant.common.money import ExactUSD
from researchassistant.contracts.model_contracts import (
    DiscoveryProvider,
    SourceSnapshot,
    StrictModel,
    _validate_aware_datetime,
)
from researchassistant.contracts.research_directions import ResearchDirection, ResearchDirections

DISCOVERY_POLICY_ID = "source-discovery-v2-2026-10-05-v1"
COMPILER_ID = "source-query-compiler-v1"
RANKING_ID = "source-candidate-ranking-v1"
PREVIEW_ID = "source-claim-preview-v1"
SEED_ID = "source-seed-expansion-v1"
CAPABILITIES_ID = "source-provider-capabilities-v1"
CONTRACT_ID = "source-discovery-contracts-v1"

Digest = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
Label = Annotated[str, Field(min_length=1, max_length=240, pattern=r"^\S(?:.*\S)?$")]
Count = Annotated[int, Field(strict=True, ge=0)]
Round = Annotated[int, Field(strict=True, ge=1, le=4)]
SearchMode = Literal["lexical", "semantic", "provider_default"]
Relationship = Literal["references", "citing", "related"]
Provider = Literal[
    DiscoveryProvider.OPENALEX,
    DiscoveryProvider.ARXIV,
    DiscoveryProvider.PUBMED,
    DiscoveryProvider.EXA,
    DiscoveryProvider.SERPSEARCH,
]


def discovery_hash(value: StrictModel | tuple[object, ...] | str) -> str:
    payload = value.model_dump(mode="json") if isinstance(value, StrictModel) else value
    encoded = (
        payload
        if isinstance(payload, str)
        else json.dumps(payload, sort_keys=True, separators=(",", ":"))
    )
    return sha256(encoded.encode()).hexdigest()


def discovery_id(run_id: UUID, family: str, identity_key: str) -> UUID:
    """Application-owned identities are namespaced to the exact run and artifact family."""
    return uuid5(run_id, f"{family}:{identity_key}")


def safe_location(value: str) -> str:
    parsed = urlsplit(value)
    if parsed.scheme != "https" and parsed.scheme != "http":
        raise ValueError("location must be an absolute HTTP(S) URL")
    if not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("location cannot contain credentials")
    secret = re.compile(r"key|token|secret|password|credential|authorization|signature", re.I)
    if any(
        secret.search(key)
        for key, _ in (
            *parse_qsl(parsed.query, keep_blank_values=True),
            *parse_qsl(parsed.fragment, keep_blank_values=True),
        )
    ):
        raise ValueError("credential-bearing URLs cannot be serialized")
    return value


class V2DiscoveryValue(StrictModel):
    model_config = ConfigDict(extra="forbid", frozen=True, validate_default=True)


class V2DiscoveryArtifact(V2DiscoveryValue):
    run_id: UUID
    artifact_id: UUID
    identity_key: Annotated[str, Field(pattern=r"^[a-zA-Z0-9][a-zA-Z0-9_.:/-]{0,239}$")]
    contract_identity: Literal["source-discovery-contracts-v1"] = CONTRACT_ID

    @model_validator(mode="after")
    def owned_identity(self) -> V2DiscoveryArtifact:
        if self.artifact_id != discovery_id(self.run_id, type(self).__name__, self.identity_key):
            raise ValueError("artifact identity is not application-owned by this run")
        return self


class V2DiscoveryPolicy(V2DiscoveryValue):
    policy_identity: Literal["source-discovery-v2-2026-10-05-v1"] = DISCOVERY_POLICY_ID
    metadata_depth: int = Field(default=20, strict=True, ge=1, le=50)
    max_pages_per_operation: int = Field(default=3, strict=True, ge=1, le=3)
    max_raw_per_round: int = Field(default=300, strict=True, ge=1, le=300)
    max_raw_per_run: int = Field(default=1000, strict=True, ge=1, le=1000)
    max_scout_per_round: int = Field(default=60, strict=True, ge=1, le=60)
    max_acquisition_per_round: int = Field(default=25, strict=True, ge=1, le=25)
    max_seeds_per_run: int = Field(default=3, strict=True, ge=1, le=3)
    max_hops: Literal[1] = 1
    unknown_request_recovery: Literal["stop"] = "stop"
    max_neighbors_per_seed: int = Field(default=10, strict=True, ge=1, le=10)
    max_expansion_per_run: int = Field(default=30, strict=True, ge=1, le=30)

    @model_validator(mode="after")
    def coherent_caps(self) -> V2DiscoveryPolicy:
        if not (
            self.max_acquisition_per_round
            <= self.max_scout_per_round
            <= self.max_raw_per_round
            <= self.max_raw_per_run
        ):
            raise ValueError("acquisition/Scout/raw round/run caps are contradictory")
        if self.max_neighbors_per_seed > self.max_expansion_per_run:
            raise ValueError("neighbor cap cannot exceed run expansion cap")
        return self


class V2ProviderCapabilities(V2DiscoveryValue):
    provider: Provider
    capability_identity: Literal[
        "source-provider-capabilities-v1", "source-provider-capabilities-v2"
    ] = CAPABILITIES_ID
    search_modes: tuple[SearchMode, ...]
    fields: tuple[Label, ...] = ()
    operators: tuple[Label, ...] = ()
    max_metadata_per_page: int = Field(strict=True, ge=1, le=10000)
    max_metadata_per_operation: int = Field(strict=True, ge=1, le=10000)
    pagination: Literal["none", "page", "offset", "cursor"]
    physical_requests_per_page: int = Field(default=1, strict=True, ge=1, le=2)
    executable_pagination: Literal["none", "page", "offset", "cursor"] = "none"
    identity_lookup: bool
    executable_identity_lookup: bool = False
    relationships: tuple[Relationship, ...] = ()
    executable_search_modes: tuple[SearchMode, ...]
    executable_relationships: tuple[Relationship, ...] = ()
    unsupported_features: tuple[Label, ...] = ()
    documentation_urls: tuple[str, ...]
    restrictions: tuple[Label, ...] = ()

    @field_validator("documentation_urls")
    @classmethod
    def safe_docs(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if not value:
            raise ValueError("capabilities require official documentation provenance")
        return tuple(safe_location(url) for url in value)

    @model_validator(mode="after")
    def consistent(self) -> V2ProviderCapabilities:
        if self.executable_pagination != "none" and self.executable_pagination != self.pagination:
            raise ValueError("executable pagination must have matching native support")
        if self.executable_identity_lookup and not self.identity_lookup:
            raise ValueError("executable lookup must have native support")
        if not self.search_modes or len(set(self.search_modes)) != len(self.search_modes):
            raise ValueError("capabilities require unique supported search modes")
        if not set(self.executable_search_modes) <= set(self.search_modes):
            raise ValueError("executable mode must have native support")
        if not set(self.executable_relationships) <= set(self.relationships):
            raise ValueError("executable relationship must have native support")
        if self.max_metadata_per_page > self.max_metadata_per_operation:
            raise ValueError("page metadata cap exceeds operation cap")
        return self

    def require_search(self, mode: SearchMode, *, executable: bool = False) -> None:
        if mode not in (self.executable_search_modes if executable else self.search_modes):
            raise ValueError(f"unsupported search mode for {self.provider}: {mode}")

    def require_relationship(self, relationship: Relationship, *, executable: bool = False) -> None:
        supported = self.executable_relationships if executable else self.relationships
        if relationship not in supported:
            raise ValueError(f"unsupported relationship for {self.provider}: {relationship}")


def _unique_gaps(value: tuple[str, ...]) -> tuple[str, ...]:
    if len(set(value)) != len(value):
        raise ValueError("target Gap IDs must be unique")
    return value


class V2ConceptGroup(V2DiscoveryValue):
    concept: Label
    synonyms: tuple[Label, ...] = Field(default=(), max_length=5)

    @model_validator(mode="after")
    def unique_terms(self) -> V2ConceptGroup:
        terms = tuple(term.casefold() for term in (self.concept, *self.synonyms))
        if len(set(terms)) != len(terms):
            raise ValueError("concept synonyms must be unique")
        return self


class V2ConceptualQuery(V2DiscoveryArtifact):
    required_concepts: tuple[V2ConceptGroup, ...] = Field(min_length=1, max_length=8)
    methods: tuple[Label, ...] = Field(default=(), max_length=5)
    outcomes: tuple[Label, ...] = Field(default=(), max_length=5)
    purpose: Literal["broad", "methods", "outcomes", "limitations", "gap"]
    direction: ResearchDirection
    provider: Provider
    round_number: Round
    target_gap_ids: tuple[Label, ...] = Field(default=(), max_length=6)
    _gaps_unique = field_validator("target_gap_ids")(_unique_gaps)

    @model_validator(mode="after")
    def explicit_gap_purpose(self) -> V2ConceptualQuery:
        if self.purpose == "gap" and not self.target_gap_ids:
            raise ValueError("gap-purpose query requires target Gap IDs")
        return self


class V2SanitizedParameter(V2DiscoveryValue):
    name: Annotated[str, Field(pattern=r"^[A-Za-z][A-Za-z0-9_.-]{0,63}$")]
    value: str | int | bool

    @model_validator(mode="after")
    def sanitized(self) -> V2SanitizedParameter:
        if re.search(
            r"key|token|secret|password|credential|authorization|signature", self.name, re.I
        ):
            raise ValueError("credential parameters cannot be serialized")
        if isinstance(self.value, str) and "://" in self.value:
            safe_location(self.value)
        return self


class V2CompiledQueryAction(V2DiscoveryArtifact):
    action_type: Literal["query"] = "query"
    conceptual_query: V2ConceptualQuery
    query_text: Annotated[str, Field(min_length=1, max_length=4000)]
    parameters: tuple[V2SanitizedParameter, ...] = ()
    mode: SearchMode
    requested_depth: int = Field(strict=True, ge=1, le=50)
    effective_depth: int = Field(strict=True, ge=1, le=50)
    compiler_identity: Literal["source-query-compiler-v1", "source-query-compiler-v2"] = COMPILER_ID
    policy: V2DiscoveryPolicy
    capabilities: V2ProviderCapabilities
    fingerprint: Digest

    @model_validator(mode="after")
    def valid_compilation(self) -> V2CompiledQueryAction:
        if self.conceptual_query.run_id != self.run_id:
            raise ValueError("conceptual query has cross-run ownership")
        if self.capabilities.provider != self.conceptual_query.provider:
            raise ValueError("query provider differs from capabilities")
        self.capabilities.require_search(self.mode, executable=True)
        if self.effective_depth > min(
            self.requested_depth,
            self.policy.metadata_depth,
            self.capabilities.max_metadata_per_operation,
        ):
            raise ValueError("effective metadata depth exceeds policy/provider request bounds")
        if self.capabilities.executable_pagination == "none" and (
            self.effective_depth > self.capabilities.max_metadata_per_page
        ):
            raise ValueError("effective depth requires unsupported pagination")
        if self.effective_depth > (
            self.capabilities.max_metadata_per_page
            * (self.policy.max_pages_per_operation // self.capabilities.physical_requests_per_page)
        ):
            raise ValueError("effective depth exceeds bounded physical pages")
        names = tuple(item.name for item in self.parameters)
        if len(names) != len(set(names)):
            raise ValueError("query parameters must be unique")
        expected = discovery_hash(self.model_dump_without_fingerprint())
        if self.fingerprint != expected:
            raise ValueError("compiled query fingerprint is stale")
        return self

    def model_dump_without_fingerprint(self) -> str:
        return json.dumps(
            self.model_dump(mode="json", exclude={"fingerprint"}),
            sort_keys=True,
            separators=(",", ":"),
        )


class V2SourceLocation(V2DiscoveryValue):
    url: str
    kind: Literal["landing", "pdf", "repository", "doi", "unknown"] = "unknown"
    same_work_basis: Literal["provider_identity", "verified_identifiers", "unverified"] = (
        "unverified"
    )
    _safe = field_validator("url")(safe_location)


def safe_identifier(value: str | None) -> str | None:
    if value is not None and "://" in value:
        safe_location(value)
    return value


def normalize_doi(value: str) -> str:
    """Validate a DOI identifier and return its stable, case-folded form."""
    normalized = value.strip()
    if normalized.casefold().startswith("doi:"):
        normalized = normalized[4:].strip()
    elif "://" in normalized:
        parsed = urlsplit(normalized)
        if (
            parsed.scheme.casefold() not in {"http", "https"}
            or (parsed.hostname or "").casefold() not in {"doi.org", "dx.doi.org"}
            or parsed.username
            or parsed.password
            or parsed.port is not None
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("DOI URL must be a credential-free doi.org location")
        normalized = parsed.path.lstrip("/")
    normalized = normalized.casefold()
    if not re.fullmatch(r"10\.\d{4,9}/[^\s\x00-\x1f\x7f]+", normalized) or normalized.endswith("/"):
        raise ValueError("DOI identifier is malformed")
    return normalized


class V2WorkIdentity(V2DiscoveryValue):
    grouping_key: Label
    doi: Label | None = None
    provider_work_id: Label | None = None
    title: str | None = None
    authors: tuple[Label, ...] | None = None
    publication_year: int | None = Field(default=None, strict=True, ge=1000, le=9999)
    resolution: Literal["verified_identifiers", "provider_identity", "unresolved"]
    _safe_provider_id = field_validator("provider_work_id")(safe_identifier)

    @field_validator("doi")
    @classmethod
    def _normalized_doi(cls, value: str | None) -> str | None:
        return normalize_doi(value) if value is not None else None

    @model_validator(mode="after")
    def meaningful_identity(self) -> V2WorkIdentity:
        if self.resolution == "verified_identifiers" and not self.doi:
            raise ValueError("verified identifier resolution requires DOI")
        if self.resolution == "provider_identity" and not self.provider_work_id:
            raise ValueError("provider resolution requires provider identity")
        return self


class V2RawDiscoveryCandidate(V2DiscoveryArtifact):
    operation_id: UUID
    attempt_id: UUID
    provider: Provider
    direction: ResearchDirection
    round_number: Round
    provider_rank: int = Field(strict=True, ge=1)
    provider_relevance: float | None = Field(default=None, allow_inf_nan=False)
    response_hash: Digest
    work: V2WorkIdentity
    locations: tuple[V2SourceLocation, ...] = ()
    abstract: str | None = None
    study_design: Label | None = None
    full_text_available: bool | None = None
    independence: Literal["unknown", "same_work", "independent_verified"] = "unknown"


class V2RankComponents(V2DiscoveryValue):
    ranking_identity: Literal["source-candidate-ranking-v1"] = RANKING_ID
    concept_overlap: float | None = Field(default=None, ge=0, le=1, allow_inf_nan=False)
    gap_relevance: float | None = Field(default=None, ge=0, le=1, allow_inf_nan=False)
    novelty: float | None = Field(default=None, ge=0, le=1, allow_inf_nan=False)
    rationale: Label


class V2NormalizedDiscoveryCandidate(V2DiscoveryArtifact):
    raw_candidates: tuple[V2RawDiscoveryCandidate, ...] = Field(min_length=1, max_length=300)
    work: V2WorkIdentity
    rank: V2RankComponents
    locations: tuple[V2SourceLocation, ...] = ()
    disposition: Literal[
        "retained",
        "duplicate",
        "excluded",
        "cap_prevented",
        "budget_prevented",
        "not_scouted",
        "shortlisted",
        "fetched",
        "unavailable",
    ]
    disposition_reason: Label

    @model_validator(mode="after")
    def same_run_and_work(self) -> V2NormalizedDiscoveryCandidate:
        if any(item.run_id != self.run_id for item in self.raw_candidates):
            raise ValueError("candidate provenance has cross-run ownership")
        if any(item.work.grouping_key != self.work.grouping_key for item in self.raw_candidates):
            raise ValueError("candidate grouping cannot merge different work identities")
        return self


class V2CandidateDisposition(V2DiscoveryArtifact):
    """A bounded audit marker may explain loss without retaining prohibited raw payloads."""

    candidate_id: UUID
    operation_id: UUID
    round_number: Round
    disposition: Literal[
        "duplicate",
        "excluded",
        "cap_prevented",
        "budget_prevented",
        "not_scouted",
        "shortlisted",
        "fetched",
        "unavailable",
    ]
    reason: Label


class V2PreviewRequest(V2DiscoveryArtifact):
    exact_claim: Annotated[str, Field(min_length=1)]
    direction: ResearchDirection
    directions: ResearchDirections
    source_id: UUID
    snapshot_id: UUID
    snapshot_hash: Digest
    preview_identity: Literal["source-claim-preview-v1"] = PREVIEW_ID

    @model_validator(mode="after")
    def permitted_lane(self) -> V2PreviewRequest:
        self.directions.require_permitted(self.direction)
        return self


class V2PreviewSpan(V2DiscoveryValue):
    start: Count
    end: int = Field(strict=True, ge=1)
    text: Annotated[str, Field(min_length=1)]
    section: Literal["methods", "results", "discussion", "abstract", "bibliography", "unknown"]
    context_before: str = ""
    context_after: str = ""
    relevance_signals: tuple[Label, ...] = ()

    @model_validator(mode="after")
    def exact_length(self) -> V2PreviewSpan:
        if self.end - self.start != len(self.text):
            raise ValueError("preview offsets do not match exact text length")
        return self


class V2PreviewResult(V2DiscoveryArtifact):
    request: V2PreviewRequest
    spans: tuple[V2PreviewSpan, ...] = Field(default=(), max_length=8)
    content_classification: Literal["full_text", "partial", "abstract_only", "shell", "unknown"]
    outcome: Literal["completed", "unavailable"]
    reason: Label

    @model_validator(mode="after")
    def owned_request(self) -> V2PreviewResult:
        if self.request.run_id != self.run_id:
            raise ValueError("preview request has cross-run ownership")
        if self.outcome == "unavailable" and self.spans:
            raise ValueError("unavailable previews cannot contain spans")
        if self.outcome == "completed" and not self.spans:
            raise ValueError("completed previews require exact spans")
        if any(a.end > b.start for a, b in zip(self.spans, self.spans[1:], strict=False)):
            raise ValueError("preview spans must be ordered and nonoverlapping")
        return self

    def require_snapshot(self, snapshot: SourceSnapshot) -> None:
        if (
            snapshot.run_id != self.run_id
            or snapshot.snapshot_id != self.request.snapshot_id
            or snapshot.snapshot_sha256 != self.request.snapshot_hash
        ):
            raise ValueError("preview snapshot ownership/hash mismatch")
        text = snapshot.normalized_text
        if sha256(text.encode()).hexdigest() != self.request.snapshot_hash:
            raise ValueError("preview snapshot text hash is stale")
        for span in self.spans:
            if (
                text[span.start : span.end] != span.text
                or text[max(0, span.start - len(span.context_before)) : span.start]
                != span.context_before
                or text[span.end : span.end + len(span.context_after)] != span.context_after
            ):
                raise ValueError("preview text/context differs from immutable snapshot")


class V2SeedEligibility(V2DiscoveryArtifact):
    candidate_id: UUID
    source_id: UUID | None = None
    snapshot_id: UUID | None = None
    work: V2WorkIdentity
    eligible: bool
    reason: Label
    seed_identity: Literal["source-seed-expansion-v1"] = SEED_ID

    @model_validator(mode="after")
    def resolved_seed(self) -> V2SeedEligibility:
        if self.eligible and (
            self.work.resolution == "unresolved" or not self.snapshot_id or not self.source_id
        ):
            raise ValueError("eligible seed requires resolved work and usable source snapshot")
        return self


class V2WorkResolution(V2DiscoveryArtifact):
    candidate_id: UUID
    provider: Provider
    work: V2WorkIdentity
    status: Literal["resolved", "unresolved", "unavailable", "pending", "skipped"]
    reason: Label
    operation_id: UUID | None = None

    @model_validator(mode="after")
    def resolution_status(self) -> V2WorkResolution:
        if self.status == "resolved" and self.work.resolution == "unresolved":
            raise ValueError("resolved result needs verified work identity")
        return self


class V2GraphNeighborAction(V2DiscoveryArtifact):
    action_type: Literal["graph_neighbors"] = "graph_neighbors"
    seed: V2SeedEligibility
    relationship: Relationship
    provider: Provider
    direction: ResearchDirection
    round_number: Round
    target_gap_ids: tuple[Label, ...] = Field(default=(), max_length=6)
    _gaps_unique = field_validator("target_gap_ids")(_unique_gaps)
    hop: Literal[1] = 1
    requested_depth: int = Field(strict=True, ge=1, le=10)
    policy: V2DiscoveryPolicy
    capabilities: V2ProviderCapabilities
    seed_identity: Literal["source-seed-expansion-v1"] = SEED_ID

    @model_validator(mode="after")
    def valid_neighbor_action(self) -> V2GraphNeighborAction:
        if self.seed.run_id != self.run_id or not self.seed.eligible:
            raise ValueError("neighbor action requires eligible seed owned by this run")
        if self.provider != self.capabilities.provider:
            raise ValueError("neighbor provider differs from capabilities")
        self.capabilities.require_relationship(self.relationship)
        if self.requested_depth > self.policy.max_neighbors_per_seed:
            raise ValueError("neighbor depth exceeds policy")
        return self


class V2ExpansionEdge(V2DiscoveryArtifact):
    action: V2GraphNeighborAction
    candidate: V2RawDiscoveryCandidate
    edge_verification: Literal["provider_reported", "unverified", "independently_verified"]

    @model_validator(mode="after")
    def edge_provenance(self) -> V2ExpansionEdge:
        if self.action.run_id != self.run_id or self.candidate.run_id != self.run_id:
            raise ValueError("expansion edge has cross-run ownership")
        if self.candidate.work.grouping_key == self.action.seed.work.grouping_key:
            raise ValueError("one-hop expansion forbids self cycles")
        if (
            self.candidate.operation_id != self.action.artifact_id
            or self.candidate.provider != self.action.provider
            or self.candidate.direction != self.action.direction
            or self.candidate.round_number != self.action.round_number
        ):
            raise ValueError("expansion candidate action provenance differs")
        return self


class V2ExpansionResult(V2DiscoveryArtifact):
    action: V2GraphNeighborAction
    edges: tuple[V2ExpansionEdge, ...] = Field(default=(), max_length=10)
    status: Literal["completed", "pending", "skipped", "unavailable", "interrupted_unknown"]
    reason: Label

    @model_validator(mode="after")
    def valid_edges(self) -> V2ExpansionResult:
        if self.action.run_id != self.run_id:
            raise ValueError("expansion action has cross-run ownership")
        if self.status != "completed" and self.edges:
            raise ValueError("incomplete expansion cannot claim completed edges")
        if len(self.edges) > self.action.requested_depth:
            raise ValueError("expansion result exceeds requested depth")
        keys = tuple(edge.candidate.work.grouping_key for edge in self.edges)
        if len(set(keys)) != len(keys):
            raise ValueError("expansion neighbors must be unique across relationships")
        if any(edge.run_id != self.run_id or edge.action != self.action for edge in self.edges):
            raise ValueError("expansion edge action ownership mismatch")
        return self


class V2DiscoveryFailure(V2DiscoveryValue):
    code: Literal[
        "unsupported",
        "invalid_request",
        "timeout",
        "connection",
        "rate_limit",
        "authentication",
        "malformed_response",
        "budget",
        "cancelled",
        "interrupted",
    ]
    retryable: bool = False
    detail: Literal[
        "provider_failure",
        "budget_exhausted",
        "unsupported_capability",
        "cancelled",
        "unknown_after_start",
    ]


class V2DiscoveryProviderBudget(V2DiscoveryValue):
    provider: Provider
    max_requests: int = Field(strict=True, ge=0)
    max_cost_usd: ExactUSD
    cost_policy_identity: Label
    reservation_per_request_usd: ExactUSD
    cost_basis: Literal["documented_free", "configured_upper_bound"]

    @model_validator(mode="after")
    def bounded_provider_budget(self) -> V2DiscoveryProviderBudget:
        caps = {
            DiscoveryProvider.SERPSEARCH: 12,
            DiscoveryProvider.EXA: 18,
            DiscoveryProvider.OPENALEX: 10,
            DiscoveryProvider.ARXIV: 6,
            DiscoveryProvider.PUBMED: 6,
        }
        if self.max_requests > caps[self.provider]:
            raise ValueError("provider request ceiling exceeds existing runtime cap")
        if self.provider is DiscoveryProvider.OPENALEX and self.max_cost_usd > Decimal("0.01"):
            raise ValueError("OpenAlex run cost ceiling exceeds existing cap")
        if self.cost_basis == "documented_free":
            if self.reservation_per_request_usd != 0 or self.max_cost_usd != 0:
                raise ValueError("documented free budget must have zero reservation and cost")
        elif self.reservation_per_request_usd == 0:
            raise ValueError("paid/unknown budget requires a conservative per-request reservation")
        return self


class V2DiscoveryBinding(V2DiscoveryArtifact):
    exact_claim: Annotated[str, Field(min_length=1)]
    directions: ResearchDirections
    providers: tuple[Provider, ...] = Field(min_length=1, max_length=5)
    policy: V2DiscoveryPolicy
    capabilities: tuple[V2ProviderCapabilities, ...]
    provider_budgets: tuple[V2DiscoveryProviderBudget, ...]
    provider_configuration_hash: Digest
    source_identity_hash: Digest
    prompt_schema_hash: Digest
    compiler_identity: Literal["source-query-compiler-v1", "source-query-compiler-v2"] = COMPILER_ID
    ranking_identity: Literal["source-candidate-ranking-v1"] = RANKING_ID
    preview_identity: Literal["source-claim-preview-v1"] = PREVIEW_ID
    seed_identity: Literal["source-seed-expansion-v1"] = SEED_ID

    @model_validator(mode="after")
    def complete_providers(self) -> V2DiscoveryBinding:
        if len(set(self.providers)) != len(self.providers):
            raise ValueError("enabled providers must be unique")
        for entries in (self.capabilities, self.provider_budgets):
            if tuple(entry.provider for entry in entries) != self.providers:
                raise ValueError(
                    "binding requires ordered capabilities/budgets for enabled providers"
                )
        return self

    @property
    def fingerprint(self) -> str:
        return discovery_hash(self)


class V2IdentityLookupAction(V2DiscoveryArtifact):
    """A physical work lookup is a distinct operation, never fabricated query text."""

    action_type: Literal["identity_lookup"] = "identity_lookup"
    candidate_id: UUID
    work_identifier: Label
    _safe_id = field_validator("work_identifier")(safe_identifier)
    provider: Provider
    direction: ResearchDirection
    round_number: Round
    target_gap_ids: tuple[Label, ...] = Field(default=(), max_length=6)
    _gaps_unique = field_validator("target_gap_ids")(_unique_gaps)
    requested_depth: Literal[1] = 1
    policy: V2DiscoveryPolicy
    capabilities: V2ProviderCapabilities

    @model_validator(mode="after")
    def valid_lookup(self) -> V2IdentityLookupAction:
        if self.provider != self.capabilities.provider or not self.capabilities.identity_lookup:
            raise ValueError("provider does not support the requested identity lookup")
        return self


class V2DiscoveryOperation(V2DiscoveryArtifact):
    binding_fingerprint: Digest
    action: V2CompiledQueryAction | V2GraphNeighborAction | V2IdentityLookupAction = Field(
        discriminator="action_type"
    )
    created_at: datetime
    _aware = field_validator("created_at")(_validate_aware_datetime)

    @model_validator(mode="after")
    def action_owner(self) -> V2DiscoveryOperation:
        if self.action.run_id != self.run_id:
            raise ValueError("operation action has cross-run ownership")
        return self


class V2ProviderAttemptStart(V2DiscoveryArtifact):
    operation_id: UUID
    binding_fingerprint: Digest
    provider: Provider
    sequence: int = Field(strict=True, ge=1, le=3)
    page_number: int = Field(strict=True, ge=1, le=3)
    request_kind: Literal["primary", "metadata"] = "primary"
    parent_attempt_id: UUID | None = None
    parent_response_hash: Digest | None = None
    parameters: tuple[V2SanitizedParameter, ...] = ()
    requested_records: int = Field(strict=True, ge=1, le=50)
    reserved_cost_usd: ExactUSD
    cost_basis: Literal["documented_free", "configured_upper_bound"]
    started_at: datetime
    _aware = field_validator("started_at")(_validate_aware_datetime)

    @model_validator(mode="after")
    def meaningful_cost(self) -> V2ProviderAttemptStart:
        if (self.request_kind == "metadata") != (
            self.parent_attempt_id is not None and self.parent_response_hash is not None
        ):
            raise ValueError("metadata subrequests require an owned completed parent response")
        if self.request_kind == "primary" and (self.parent_attempt_id or self.parent_response_hash):
            raise ValueError("primary request cannot claim a metadata response parent")
        names = tuple(item.name for item in self.parameters)
        if len(names) != len(set(names)):
            raise ValueError("physical request parameters must be unique")
        if self.cost_basis == "documented_free" and self.reserved_cost_usd != 0:
            raise ValueError("documented free requests must reserve zero cost")
        if self.cost_basis == "configured_upper_bound" and self.reserved_cost_usd == 0:
            raise ValueError("unknown paid request cannot invent zero exposure")
        return self


class V2ProviderAttemptCompletion(V2DiscoveryArtifact):
    attempt_id: UUID
    operation_id: UUID
    status: Literal["completed", "failed", "interrupted_unknown"]
    response_hash: Digest | None = None
    result_ids: tuple[UUID, ...] = ()
    metadata_records: Count = 0
    failure: V2DiscoveryFailure | None = None
    actual_cost_usd: ExactUSD | None = None
    cost_basis: Literal["reported", "documented_free", "unknown"]
    completed_at: datetime
    elapsed_ms: int | None = Field(default=None, strict=True, ge=0)
    _aware = field_validator("completed_at")(_validate_aware_datetime)

    @model_validator(mode="after")
    def consistent_completion(self) -> V2ProviderAttemptCompletion:
        if (self.status == "completed") != (self.failure is None):
            raise ValueError("attempt status and typed failure must agree")
        if self.status == "completed" and self.response_hash is None:
            raise ValueError("completed request requires response identity hash")
        if (self.actual_cost_usd is None) != (self.cost_basis == "unknown"):
            raise ValueError("unknown usage must retain unknown cost")
        if self.cost_basis == "documented_free" and self.actual_cost_usd != 0:
            raise ValueError("documented free completion cannot claim nonzero cost")
        if self.status == "interrupted_unknown" and self.cost_basis != "unknown":
            raise ValueError("interrupted request must retain unknown cost exposure")
        if len(self.result_ids) > self.metadata_records:
            raise ValueError("result identities exceed reported metadata record count")
        if len(set(self.result_ids)) != len(self.result_ids):
            raise ValueError("result identities must be unique")
        return self


class V2DiscoveryAuditCounters(V2DiscoveryArtifact):
    logical_queries: Count = 0
    graph_operations: Count = 0
    http_requests: Count = 0
    metadata_records: Count = 0
    unique_work_candidates: Count = 0
    acquisition_attempts: Count = 0
    usable_snapshots: Count = 0
    admitted_evidence: Count = 0
    unknown_requests: Count = 0


class V2DiscoveryClientSettings(V2DiscoveryValue):
    """Absent settings explicitly retain the previous runtime policy."""

    selected_policy: Literal["source-discovery-v2-2026-10-05-v1"] | None = None
    policy: V2DiscoveryPolicy | None = None

    @model_validator(mode="after")
    def explicit_selection(self) -> V2DiscoveryClientSettings:
        if (self.selected_policy is None) != (self.policy is None):
            raise ValueError("new settings require an explicitly selected discovery policy")
        return self
