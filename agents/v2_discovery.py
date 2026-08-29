"""Fresh-v2 Phase-4 discovery normalization, identity clustering, and batched Scout.

The module deliberately operates on metadata-only ``SearchResult`` values.  It never
acquires a page, interprets provider snippets as evidence, or changes historical
discovery ranking.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path
from uuid import NAMESPACE_URL, UUID, uuid5

from pydantic import ConfigDict

from models import (
    CrossrefIdentityMetadata,
    DiscoveryMetadataEntry,
    DiscoveryProvenance,
    DiscoveryProviderReference,
    NormalizedDiscoveryItem,
    ResearchDirections,
    ScoutBatch,
    ScoutBatchAudit,
    ScoutCandidate,
    ScoutItem,
    SourceCluster,
    StrictModel,
    V2AdaptiveRoundPlan,
    V2AdaptiveSearchQuery,
    V2DiscoveryScoutOutput,
    V2InitialPlannerOutput,
    V2RoundOneSearchQuery,
    V2ScoutRequest,
)
from providers.llm import (
    V2_LLM_ROUTING,
    LLMInvocationError,
    LLMProvider,
    LLMRequest,
    LLMStage,
    invoke_llm,
    load_prompt_file,
    render_stage_prompt,
)
from providers.ranking import canonical_discovery_url
from providers.search import SearchResult
from providers.v2_budget import V2CancellationRequested
from providers.v2_routing import V2RoutingConfig
from store import insert_v2_artifact, read_v2_artifact

V2_SCOUT_PROMPT_PATH = Path(__file__).resolve().parents[1] / "prompts" / "v2_scout.md"
V2_SCOUT_BATCH_SIZE = 30
V2_SCOUT_ARTIFACT_KEY = "phase-4-discovery-scout"
_TITLE_TOKEN_RE = re.compile(r"[a-z0-9]+")
_DOI_PREFIX_RE = re.compile(r"^(?:https?://(?:dx\.)?doi\.org/|doi:)\s*", re.IGNORECASE)


class V2DiscoveryResponse(StrictModel):
    """One provider response retained beside its application-owned round query."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    query: V2RoundOneSearchQuery | V2AdaptiveSearchQuery
    results: tuple[SearchResult, ...]


class CrossrefEnricher(StrictModel):
    """Small typed adapter boundary for optional, non-fatal source identity lookup."""

    model_config = ConfigDict(extra="forbid", frozen=True, arbitrary_types_allowed=True)

    resolve: object


class V2DiscoveryScoutRunResult(StrictModel):
    """A persisted or newly-computed Phase-4 result without retrieval side effects."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    output: V2DiscoveryScoutOutput
    resumed: bool


def normalize_discovery_responses(
    *,
    run_id: UUID,
    directions: ResearchDirections,
    responses: Sequence[V2DiscoveryResponse],
    discovered_at: datetime,
    crossref_resolver: Callable[[str], CrossrefIdentityMetadata] | None = None,
    cancellation_requested: Callable[[], bool] | None = None,
) -> tuple[NormalizedDiscoveryItem, ...]:
    """Normalize every provider result while retaining all provider/query provenance."""
    _require_aware(discovered_at, "discovered_at")
    items: list[NormalizedDiscoveryItem] = []
    seen_ids: set[UUID] = set()
    for response in responses:
        query = response.query
        if query.run_id != run_id:
            raise ValueError("discovery response query belongs to another run")
        directions.require_permitted(query.direction)
        for result in response.results:
            _raise_if_cancelled(cancellation_requested)
            item_id = _item_id(run_id, query, result.rank, result.original_url)
            if item_id in seen_ids:
                raise ValueError("stable discovery item IDs must be unique")
            seen_ids.add(item_id)
            provider_doi = _normalized_doi(result.metadata.doi)
            crossref = _crossref_identity(provider_doi, crossref_resolver)
            doi = crossref.doi if crossref and crossref.doi else provider_doi
            item = NormalizedDiscoveryItem(
                run_id=run_id,
                item_id=item_id,
                provider=query.provider,
                query_id=query.query_id,
                query_text=query.query_text,
                direction=query.direction,
                round_number=query.round_number,
                provider_rank=result.rank,
                source_url=result.original_url,
                canonical_url=canonical_discovery_url(result.original_url),
                title=crossref.canonical_title
                if crossref and crossref.canonical_title
                else result.title or None,
                snippet=result.snippet,
                abstract=_metadata_string(result, "abstract"),
                doi=doi,
                authors=_authors(result, crossref),
                publication_date=(
                    crossref.publication_date
                    if crossref and crossref.publication_date
                    else result.metadata.published_at
                ),
                source_type=result.metadata.work_type or result.metadata.category,
                provider_metadata=_metadata_entries(result),
                provenance_chain=(
                    DiscoveryProvenance(
                        provider=query.provider,
                        query_id=query.query_id,
                        query_text=query.query_text,
                        direction=query.direction,
                        round_number=query.round_number,
                        provider_rank=result.rank,
                        original_url=result.original_url,
                    ),
                ),
                crossref=crossref,
                discovered_at=discovered_at,
            )
            items.append(item)
    return tuple(items)


def cluster_discovery_items(items: Sequence[NormalizedDiscoveryItem]) -> tuple[SourceCluster, ...]:
    """Conservatively union only exact URL/DOI/title or exact author-year-title identity."""
    if not items:
        return ()
    run_ids = {item.run_id for item in items}
    if len(run_ids) != 1:
        raise ValueError("a discovery pool cannot cluster more than one run")
    parent = list(range(len(items)))

    def find(index: int) -> int:
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    def union(left: int, right: int) -> None:
        left_root, right_root = find(left), find(right)
        if left_root != right_root:
            parent[right_root] = left_root

    for left, item in enumerate(items):
        for right in range(left):
            if _same_source(item, items[right]):
                union(left, right)
    groups: dict[int, list[NormalizedDiscoveryItem]] = {}
    for index, item in enumerate(items):
        groups.setdefault(find(index), []).append(item)
    clusters: list[SourceCluster] = []
    for members in groups.values():
        ordered = sorted(members, key=lambda item: (item.canonical_url, str(item.item_id)))
        preferred = min(ordered, key=_preferred_url_key)
        urls = tuple(
            sorted(
                {member.source_url for member in ordered}
                | {member.canonical_url for member in ordered}
            )
        )
        cluster_id = uuid5(
            NAMESPACE_URL,
            "researchassistant-v2-source-cluster::"
            f"{preferred.run_id}::{preferred.canonical_url}::"
            + "::".join(str(member.item_id) for member in ordered),
        )
        clusters.append(
            SourceCluster(
                cluster_id=cluster_id,
                preferred_url=preferred.source_url,
                canonical_url=preferred.canonical_url,
                alternate_urls=tuple(
                    url
                    for url in urls
                    if url not in {preferred.source_url, preferred.canonical_url}
                ),
                item_ids=tuple(member.item_id for member in ordered),
                provider_references=tuple(
                    DiscoveryProviderReference(
                        provider=member.provider,
                        item_id=member.item_id,
                        provider_rank=member.provider_rank,
                    )
                    for member in ordered
                ),
                query_references=tuple(dict.fromkeys(member.query_id for member in ordered)),
                metadata_provenance=tuple(
                    provenance for member in ordered for provenance in member.provenance_chain
                ),
            )
        )
    return tuple(
        sorted(
            clusters,
            key=lambda cluster: (cluster.canonical_url, str(cluster.cluster_id)),
        )
    )


def run_v2_discovery_and_scout(
    *,
    db_path: str | Path,
    planner_output: V2InitialPlannerOutput | V2AdaptiveRoundPlan,
    responses: Sequence[V2DiscoveryResponse],
    llm_provider: LLMProvider,
    routing_config: V2RoutingConfig,
    clock: Callable[[], datetime] | None = None,
    crossref_resolver: Callable[[str], CrossrefIdentityMetadata] | None = None,
    cancellation_requested: Callable[[], bool] | None = None,
) -> V2DiscoveryScoutRunResult:
    """Persist or resume one round of normalized discovery and batched Scout decisions."""
    now = clock or _utc_now
    completed_at = now()
    _require_aware(completed_at, "clock result")
    try:
        existing = read_v2_artifact(
            str(db_path), planner_output.run_id, _artifact_key(planner_output)
        )
    except KeyError:
        existing = None
    if existing is not None:
        output = V2DiscoveryScoutOutput.model_validate_json(existing.payload_json)
        if output.directions != planner_output.directions:
            raise ValueError("persisted discovery output directions do not match the initial plan")
        return V2DiscoveryScoutRunResult(output=output, resumed=True)
    _require_mimo_scout_route(routing_config)
    items = normalize_discovery_responses(
        run_id=planner_output.run_id,
        directions=planner_output.directions,
        responses=responses,
        discovered_at=completed_at,
        crossref_resolver=crossref_resolver,
        cancellation_requested=cancellation_requested,
    )
    clusters = cluster_discovery_items(items)
    batches, audits = _run_scout_batches(
        run_id=planner_output.run_id,
        directions=planner_output.directions,
        items=items,
        llm_provider=llm_provider,
        clock=now,
    )
    output = V2DiscoveryScoutOutput(
        run_id=planner_output.run_id,
        directions=planner_output.directions,
        items=items,
        clusters=clusters,
        scout_batches=batches,
        scout_audits=audits,
        completed_at=completed_at,
    )
    insert_v2_artifact(str(db_path), _artifact_key(planner_output), output, completed_at)
    return V2DiscoveryScoutRunResult(output=output, resumed=False)


def _raise_if_cancelled(callback: Callable[[], bool] | None) -> None:
    if callback is not None and callback():
        raise V2CancellationRequested("v2 cancellation was observed before discovery work")


def scout_ordered_item_ids(output: V2DiscoveryScoutOutput) -> tuple[UUID, ...]:
    """Return retrieve/maybe candidates in deterministic provider-neutral fallback order."""
    decisions = {
        item.item_id: item.decision for batch in output.scout_batches for item in batch.items
    }
    order = {"retrieve": 0, "maybe": 1, "skip": 2}
    return tuple(
        item.item_id
        for item in sorted(
            output.items,
            key=lambda item: (
                order[_decision_value(item.item_id, decisions)],
                item.canonical_url,
                item.provider_rank,
                str(item.item_id),
            ),
        )
        if decisions.get(item.item_id) is not None and decisions[item.item_id].value != "skip"
    )


def _run_scout_batches(
    *,
    run_id: UUID,
    directions: ResearchDirections,
    items: tuple[NormalizedDiscoveryItem, ...],
    llm_provider: LLMProvider,
    clock: Callable[[], datetime],
) -> tuple[tuple[ScoutBatch, ...], tuple[ScoutBatchAudit, ...]]:
    prompt = load_prompt_file(V2_SCOUT_PROMPT_PATH, expected_stage=LLMStage.SCOUT)
    batches: list[ScoutBatch] = []
    audits: list[ScoutBatchAudit] = []
    for start in range(0, len(items), V2_SCOUT_BATCH_SIZE):
        batch_items = items[start : start + V2_SCOUT_BATCH_SIZE]
        request_input = V2ScoutRequest(
            run_id=run_id,
            directions=directions,
            batch_number=start // V2_SCOUT_BATCH_SIZE + 1,
            candidates=tuple(_scout_candidate(item) for item in batch_items),
        )
        last_error: LLMInvocationError | None = None
        response: ScoutBatch | None = None
        attempted = 0
        for _ in range(2):
            attempted += 1
            request = LLMRequest(
                run_id=run_id,
                stage=LLMStage.SCOUT,
                prompt=prompt,
                rendered_prompt=render_stage_prompt(prompt, request_input, ScoutBatch),
                input_artifact=request_input,
                input_artifact_ids=(run_id,),
                requested_output_type=ScoutBatch,
                model_alias=V2_LLM_ROUTING.for_stage(LLMStage.SCOUT).primary,
                generation=V2_LLM_ROUTING.for_stage(LLMStage.SCOUT).generation,
            )
            try:
                invoked = invoke_llm(llm_provider, request, clock=clock)
                candidate = invoked.output_artifact
                if not isinstance(candidate, ScoutBatch):
                    raise ValueError("Scout returned an unexpected typed artifact")
                _validate_scout_mapping(request_input, candidate)
                response = candidate
                break
            except (LLMInvocationError, ValueError) as exc:
                last_error = exc if isinstance(exc, LLMInvocationError) else None
        if response is None:
            response = ScoutBatch(
                run_id=run_id,
                items=tuple(
                    ScoutItem(
                        item_id=candidate.item_id,
                        decision="maybe",
                        rationale="Scout unavailable; deterministic ranking fallback.",
                    )
                    for candidate in request_input.candidates
                ),
            )
            failure = str(last_error) if last_error is not None else "Scout response mapping failed"
            audits.append(
                ScoutBatchAudit(
                    batch_number=request_input.batch_number,
                    attempted_calls=attempted,
                    fallback_used=True,
                    failure=failure,
                )
            )
        else:
            audits.append(
                ScoutBatchAudit(batch_number=request_input.batch_number, attempted_calls=attempted)
            )
        batches.append(response)
    return tuple(batches), tuple(audits)


def _validate_scout_mapping(request: V2ScoutRequest, response: ScoutBatch) -> None:
    if response.run_id != request.run_id:
        raise ValueError("Scout response run_id does not match its request")
    expected = {item.item_id for item in request.candidates}
    actual = {item.item_id for item in response.items}
    if actual - expected:
        raise ValueError("Scout response contains an unknown item ID")
    if expected - actual:
        raise ValueError("Scout response is missing a decision")
    if len(response.items) != len(actual):
        raise ValueError("Scout response contains duplicate item IDs")


def _decision_value(item_id: UUID, decisions: dict[UUID, object]) -> str:
    decision = decisions.get(item_id)
    return decision.value if decision is not None else "maybe"


def _item_id(
    run_id: UUID,
    query: V2RoundOneSearchQuery | V2AdaptiveSearchQuery,
    rank: int,
    url: str,
) -> UUID:
    return uuid5(
        NAMESPACE_URL,
        f"researchassistant-v2-discovery::{run_id}::{query.query_id}::{rank}::{canonical_discovery_url(url)}",
    )


def _artifact_key(planner_output: V2InitialPlannerOutput | V2AdaptiveRoundPlan) -> str:
    round_number = (
        1 if isinstance(planner_output, V2InitialPlannerOutput) else planner_output.round_number
    )
    return (
        V2_SCOUT_ARTIFACT_KEY
        if round_number == 1
        else "post-phase-13-round-4-discovery-scout-v1"
        if round_number == 4
        else f"phase-7-round-{round_number}-discovery-scout"
    )


def _normalized_doi(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = _DOI_PREFIX_RE.sub("", value.strip()).rstrip("/.,;)").casefold()
    return normalized or None


def _crossref_identity(
    doi: str | None,
    resolver: Callable[[str], CrossrefIdentityMetadata] | None,
) -> CrossrefIdentityMetadata | None:
    if doi is None or resolver is None:
        return None
    try:
        resolved = resolver(doi)
        if not isinstance(resolved, CrossrefIdentityMetadata):
            raise TypeError("Crossref resolver must return CrossrefIdentityMetadata")
        return resolved
    except Exception as exc:
        return CrossrefIdentityMetadata(doi=doi, verified=False, failure_code=type(exc).__name__)


def _authors(result: SearchResult, crossref: CrossrefIdentityMetadata | None) -> tuple[str, ...]:
    if crossref and crossref.canonical_authors:
        return crossref.canonical_authors
    return (result.metadata.author,) if result.metadata.author else ()


def _metadata_entries(result: SearchResult) -> tuple[DiscoveryMetadataEntry, ...]:
    values = result.metadata.model_dump(mode="json", exclude_none=True)
    values["relevance_score"] = result.relevance_score
    return tuple(
        DiscoveryMetadataEntry(
            key=key,
            value_json=json.dumps(value, sort_keys=True, separators=(",", ":")),
        )
        for key, value in sorted(values.items())
        if value is not None
    )


def _metadata_string(result: SearchResult, key: str) -> str | None:
    if key == "abstract":
        return result.metadata.abstract
    raise ValueError(f"unknown normalized discovery metadata field: {key}")


def _same_source(left: NormalizedDiscoveryItem, right: NormalizedDiscoveryItem) -> bool:
    if left.canonical_url == right.canonical_url:
        return True
    if left.doi and right.doi and left.doi == right.doi:
        return True
    left_title, right_title = _title_key(left.title), _title_key(right.title)
    if left_title and left_title == right_title:
        return True
    return bool(
        left_title
        and left_title == right_title
        and left.authors
        and right.authors
        and _author_key(left.authors) == _author_key(right.authors)
        and _year(left.publication_date) is not None
        and _year(left.publication_date) == _year(right.publication_date)
    )


def _title_key(value: str | None) -> str:
    return " ".join(_TITLE_TOKEN_RE.findall(value.casefold())) if value else ""


def _author_key(authors: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(sorted(" ".join(_TITLE_TOKEN_RE.findall(author.casefold())) for author in authors))


def _year(value: str | None) -> str | None:
    match = re.search(r"(?:19|20)\d{2}", value or "")
    return match.group(0) if match else None


def _preferred_url_key(item: NormalizedDiscoveryItem) -> tuple[int, str, str]:
    return (0 if item.doi else 1, item.canonical_url, str(item.item_id))


def _scout_candidate(item: NormalizedDiscoveryItem) -> ScoutCandidate:
    return ScoutCandidate(
        item_id=item.item_id,
        direction=item.direction,
        title=item.title,
        source_url=item.source_url,
        snippet=item.snippet,
        abstract=item.abstract,
        doi=item.doi,
        authors=item.authors,
        publication_date=item.publication_date,
        source_type=item.source_type,
    )


def _require_mimo_scout_route(routing_config: V2RoutingConfig) -> None:
    route = routing_config.preflight().for_stage(LLMStage.SCOUT)
    if route.logical_alias.value != "mimo-v2.5" or route.physical_model != "mimo-v2.5":
        raise ValueError("the v2 Scout requires MiMo-v2.5")


def _require_aware(value: datetime, name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")


def _utc_now() -> datetime:
    return datetime.now(UTC)
