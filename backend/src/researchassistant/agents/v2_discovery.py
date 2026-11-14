"""Fresh-v2 Phase-4 discovery normalization, identity clustering, and batched Scout.

The module uses discovery and bibliographic metadata for screening. It never
acquires source full text, interprets provider snippets as evidence, or changes
historical discovery ranking.
"""

from __future__ import annotations

import hashlib
import ipaddress
import json
import re
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from contextlib import nullcontext
from contextvars import copy_context
from datetime import UTC, datetime
from importlib.resources.abc import Traversable
from pathlib import Path
from threading import Event
from typing import Literal
from urllib.parse import urlsplit
from uuid import NAMESPACE_URL, UUID, uuid5

from pydantic import ConfigDict

from researchassistant.agents.v2_stage_checkpoint import (
    V2ScoutRoundCheckpoint,
    V2StageAttemptCheckpoint,
    V2StageOutcomeCheckpoint,
    checkpoint_hash,
    read_checkpoint,
    save_stage_outcome,
    stage_attempt,
    stage_request_hash,
)
from researchassistant.common.resources import prompt_resource
from researchassistant.contracts.discovery_v2 import (
    V2DiscoveryBinding,
    V2DiscoveryPolicy,
    V2MetadataDiscoveryPolicy,
    normalize_doi,
    safe_location,
)
from researchassistant.contracts.metadata_ranking import (
    MetadataIdentityConflict,
    MetadataRank,
    V2MetadataRankingArtifact,
    V2ScoutDisposition,
)
from researchassistant.contracts.models import (
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
from researchassistant.contracts.research_discovery import (
    V2ClaimScoutRequest,
    V2LateDiscoveryMirror,
)
from researchassistant.contracts.search import SearchResult
from researchassistant.evidence.paper_identity import paper_title_key
from researchassistant.providers.llm import (
    V2_LLM_ROUTING,
    LLMInvocationError,
    LLMProvider,
    LLMRequest,
    LLMStage,
    ModelAlias,
    invoke_llm,
    load_prompt_file,
    render_stage_prompt,
)
from researchassistant.providers.nber_metadata import (
    NberPaperMetadata,
    is_placeholder_title,
    nber_metadata_url,
    nber_paper_number,
    resolve_nber_metadata,
)
from researchassistant.providers.pricing import conservative_token_estimate
from researchassistant.providers.ranking import canonical_discovery_url
from researchassistant.providers.v2_budget import (
    V2BudgetSnapshot,
    V2CancellationRequested,
)
from researchassistant.providers.v2_routing import V2RoutingConfig
from researchassistant.research.discovery_policy import (
    safe_optional_model_prefix,
    stable_work_key,
)
from researchassistant.research.metadata_ranking import (
    EXACT_URL_RANKING_IDENTITY,
    RANKING_IDENTITIES,
    RANKING_IDENTITY,
    fair_ranked_ids,
    rank_metadata,
)
from researchassistant.storage.discovery_store import read_discovery_binding
from researchassistant.storage.sqlite_policy import overlapping_database_writes
from researchassistant.storage.store import (
    insert_v2_artifact,
    insert_v2_artifact_batch,
    read_v2_artifact,
)

V2_SCOUT_PROMPT_PATH = prompt_resource("v2_scout.md")
V2_SCOUT_V2_PROMPT_PATH = prompt_resource("v2_scout_v2.md")
V2_SCOUT_V3_PROMPT_PATH = prompt_resource("v2_scout_v3.md")
V2_SCOUT_BATCH_SIZE = 20
V2_FRESH_SCOUT_BATCH_SIZE = 15
V2_SCOUT_MAX_WORKERS = 3
V2_SCOUT_ARTIFACT_KEY = "phase-4-discovery-scout"
V2_RANKING_ARTIFACT_PREFIX = "phase-3-metadata-ranking-round-"
_TITLE_TOKEN_RE = re.compile(r"[a-z0-9]+")
_DOI_PREFIX_RE = re.compile(r"^(?:https?://(?:dx\.)?doi\.org/|doi:)\s*", re.IGNORECASE)


ScoutHandoff = Callable[
    [V2DiscoveryScoutOutput, V2MetadataRankingArtifact, tuple[LLMRequest, ...], bool],
    None,
]


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
    ranking_artifact: V2MetadataRankingArtifact | None = None


class V2NberMetadataCheckpoint(StrictModel):
    """An intent consumes the lookup even if interrupted before recording the outcome."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: UUID
    paper_number: str
    metadata: NberPaperMetadata | None = None


def _repair_nber_metadata(
    db_path: str,
    run_id: UUID,
    number: str,
    clock: Callable[[], datetime],
    cancellation_requested: Callable[[], bool] | None,
) -> NberPaperMetadata | None:
    key = f"scout-nber-metadata-v1/{number}"
    _raise_if_cancelled(cancellation_requested)
    intent = read_checkpoint(db_path, run_id, key, V2NberMetadataCheckpoint)
    if intent is not None:
        outcome = read_checkpoint(db_path, run_id, key + "/outcome", V2NberMetadataCheckpoint)
        if intent.paper_number != number or (
            outcome is not None and outcome.paper_number != number
        ):
            raise ValueError("saved NBER lookup belongs to another paper")
        return outcome.metadata if outcome is not None else None

    # The production worker owns the database lock across this request and its outcome.
    intent = V2NberMetadataCheckpoint(run_id=run_id, paper_number=number)
    insert_v2_artifact(db_path, key, intent, clock())
    metadata = resolve_nber_metadata(number)
    outcome = intent.model_copy(update={"metadata": metadata})
    insert_v2_artifact(db_path, key + "/outcome", outcome, clock())
    _raise_if_cancelled(cancellation_requested)
    return metadata


def normalize_discovery_responses(
    *,
    run_id: UUID,
    directions: ResearchDirections,
    responses: Sequence[V2DiscoveryResponse],
    discovered_at: datetime,
    crossref_resolver: Callable[[str], CrossrefIdentityMetadata] | None = None,
    cancellation_requested: Callable[[], bool] | None = None,
    url_identity_version: Literal[1, 2] = 2,
    nber_resolver: Callable[[str], NberPaperMetadata | None] | None = None,
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
            item_id = _item_id(
                run_id,
                query,
                result.rank,
                result.original_url,
                url_identity_version=url_identity_version,
            )
            if item_id in seen_ids:
                raise ValueError("stable discovery item IDs must be unique")
            seen_ids.add(item_id)
            provider_doi = _normalized_doi(
                result.metadata.doi,
                exact_identifiers=query.compiled_query is not None
                or (isinstance(query, V2AdaptiveSearchQuery) and query.graph_action is not None),
            )
            number = (
                nber_paper_number(result.original_url)
                if nber_resolver is not None and is_placeholder_title(result.title)
                else None
            )
            repaired = nber_resolver(number) if nber_resolver and number is not None else None
            crossref = (
                _crossref_identity(provider_doi, crossref_resolver) if repaired is None else None
            )
            provider_metadata = _metadata_entries(result)
            if repaired is not None and number is not None:
                provider_metadata += (
                    DiscoveryMetadataEntry(
                        key="nber_metadata_repair",
                        value_json=json.dumps(
                            {
                                "handle": repaired.handle,
                                "source_url": nber_metadata_url(number),
                            }
                        ),
                    ),
                )
            title = result.title or None
            abstract = _metadata_string(result, "abstract")
            if repaired is not None:
                title = repaired.title
                if not (abstract or "").strip():
                    abstract = repaired.abstract
            elif crossref and crossref.canonical_title:
                title = crossref.canonical_title
            doi = crossref.doi if crossref and crossref.doi else provider_doi
            item = NormalizedDiscoveryItem(
                run_id=run_id,
                item_id=item_id,
                provider=query.provider,
                query_id=query.query_id,
                query_text=query.query_text,
                graph_action=(
                    query.graph_action if isinstance(query, V2AdaptiveSearchQuery) else None
                ),
                direction=query.direction,
                round_number=query.round_number,
                provider_rank=result.rank,
                source_url=result.original_url,
                canonical_url=canonical_discovery_url(
                    result.original_url, version=url_identity_version
                ),
                title=title,
                snippet=result.snippet,
                abstract=abstract,
                doi=doi,
                authors=_authors(result, crossref),
                publication_date=(
                    crossref.publication_date
                    if crossref and crossref.publication_date
                    else result.metadata.published_at
                ),
                source_type=result.metadata.work_type or result.metadata.category,
                provider_metadata=provider_metadata,
                provenance_chain=(
                    DiscoveryProvenance(
                        provider=query.provider,
                        query_id=query.query_id,
                        query_text=query.query_text,
                        graph_action=(
                            query.graph_action if isinstance(query, V2AdaptiveSearchQuery) else None
                        ),
                        direction=query.direction,
                        round_number=query.round_number,
                        provider_rank=result.rank,
                        original_url=result.original_url,
                        targeted_gap_ids=(
                            query.targeted_gap_ids
                            if isinstance(query, V2AdaptiveSearchQuery)
                            else ()
                        ),
                    ),
                ),
                crossref=crossref,
                discovered_at=discovered_at,
            )
            items.append(item)
    return tuple(items)


def cluster_discovery_items(
    items: Sequence[NormalizedDiscoveryItem],
    *,
    include_provider_locations: bool = False,
    require_identity: bool = False,
    ignore_placeholder_titles: bool = False,
) -> tuple[SourceCluster, ...]:
    """Group discovery locations, with verified anchors required by current ranking."""
    if not items:
        return ()
    run_ids = {item.run_id for item in items}
    if len(run_ids) != 1:
        raise ValueError("a discovery pool cannot cluster more than one run")
    parent = list(range(len(items)))
    dois = [
        _normalized_doi(item.doi, exact_identifiers=True) if require_identity else item.doi
        for item in items
    ]
    root_dois = [{doi} if doi else set() for doi in dois]
    root_provider_ids = [
        _provider_identity_anchors(item)
        if include_provider_locations or require_identity
        else set()
        for item in items
    ]
    root_titles = [
        {title}
        if require_identity
        and (title := paper_title_key(item.title))
        and not (ignore_placeholder_titles and not _usable_reconsideration_title(item))
        else set()
        for item in items
    ]

    def find(index: int) -> int:
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    def union(left: int, right: int, kind: str) -> None:
        left_root, right_root = find(left), find(right)
        if left_root != right_root:
            combined_dois = root_dois[left_root] | root_dois[right_root]
            # Fresh metadata pools must not replace a distinct identified paper
            # merely because its title matches. Guard the entire union component
            # so an unidentified record cannot bridge contradictory DOI anchors.
            if (include_provider_locations or require_identity) and len(combined_dois) > 1:
                return
            combined_titles = root_titles[left_root] | root_titles[right_root]
            # An ambiguous DOI attached to different titles is a conflict, not proof of a mirror.
            if require_identity and kind == "doi" and len(combined_titles) > 1:
                return
            combined_ids = root_provider_ids[left_root] | root_provider_ids[right_root]
            shared_doi = bool(root_dois[left_root] & root_dois[right_root])
            if (
                (include_provider_locations or require_identity)
                and not shared_doi
                and any(
                    len({identifier for provider, identifier in combined_ids if provider == owner})
                    > 1
                    for owner, _identifier in combined_ids
                )
            ):
                return
            parent[right_root] = left_root
            root_dois[left_root] = combined_dois
            root_provider_ids[left_root] = combined_ids
            root_titles[left_root] = combined_titles

    # Each identity predicate is equality on a normalized token. Bucket candidates by
    # token and union only bucket members, preserving the prior equivalence semantics
    # without comparing every pair in a large metadata pool.
    identity_buckets: dict[tuple[str, str], list[int]] = {}
    for index, item in enumerate(items):
        keys = [("url", item.canonical_url)]
        if dois[index]:
            keys.append(("doi", dois[index]))
        if require_identity:
            keys.extend(sorted(root_provider_ids[index]))
        elif title := _title_key(item.title):
            keys.append(("title", title))
        for key in keys:
            prior_members = identity_buckets.setdefault(key, [])
            for prior in prior_members:
                union(index, prior, key[0])
            prior_members.append(index)
            # Keep one representative per component, preserving linear behavior
            # for duplicate-heavy historical pools and avoiding repeated unions.
            identity_buckets[key] = list(dict.fromkeys(find(member) for member in prior_members))
    groups: dict[int, list[NormalizedDiscoveryItem]] = {}
    for index, item in enumerate(items):
        groups.setdefault(find(index), []).append(item)
    clusters: list[SourceCluster] = []
    for members in groups.values():
        ordered = sorted(members, key=lambda item: (item.canonical_url, str(item.item_id)))
        preferred = min(
            ordered,
            key=lambda item: (
                not bool(_provider_full_text_locations(item)) if require_identity else False,
                _preferred_url_key(item),
            ),
        )
        provider_locations = (
            {location for member in ordered for location in _provider_full_text_locations(member)}
            if include_provider_locations
            else set()
        )
        urls = tuple(
            sorted(
                {member.source_url for member in ordered}
                | {member.canonical_url for member in ordered}
                | provider_locations
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


def _clustered_work_keys(
    items: tuple[NormalizedDiscoveryItem, ...], clusters: tuple[SourceCluster, ...]
) -> dict[UUID, str]:
    by_id = {item.item_id: item for item in items}
    cluster_keys = []
    for cluster in clusters:
        members = [by_id[item_id] for item_id in cluster.item_ids]
        doi = next(
            (doi for item in members if (doi := _normalized_doi(item.doi, exact_identifiers=True))),
            None,
        )
        anchors = sorted(
            {anchor for member in members for anchor in _provider_identity_anchors(member)}
        )
        key = (
            stable_work_key(doi=doi, canonical_url=cluster.canonical_url, url_identity_version=2)
            if doi or not anchors
            else "provider:" + hashlib.sha256(":".join(anchors[0]).encode()).hexdigest()
        )
        if len(key) > 512:
            key = "doi:sha256:" + hashlib.sha256(key.encode()).hexdigest()
        cluster_keys.append(key)
    duplicate_keys = {key for key, count in Counter(cluster_keys).items() if count > 1}
    return {
        item_id: (
            "conflict:" + hashlib.sha256(f"{key}/{cluster.cluster_id}".encode()).hexdigest()
            if key in duplicate_keys
            else key
        )
        for cluster, key in zip(clusters, cluster_keys, strict=True)
        for item_id in cluster.item_ids
    }


def _progressive_clusters(
    items: tuple[NormalizedDiscoveryItem, ...],
    prefix: V2DiscoveryScoutOutput,
    *,
    allow_reconsideration: bool = False,
) -> tuple[
    tuple[SourceCluster, ...],
    tuple[V2LateDiscoveryMirror, ...],
    frozenset[UUID],
    dict[UUID, UUID],
]:
    combined = cluster_discovery_items(
        items, include_provider_locations=True, require_identity=True
    )
    scouted = {
        item.item_id: item.decision for batch in prefix.scout_batches for item in batch.items
    }
    owned = {item_id: cluster for cluster in prefix.clusters for item_id in cluster.item_ids}
    by_id = {item.item_id: item for item in items}
    covered = {
        item_id
        for cluster in prefix.clusters
        if set(cluster.item_ids) & scouted.keys()
        for item_id in cluster.item_ids
    }
    mirrors: list[V2LateDiscoveryMirror] = []
    late_clusters: list[SourceCluster] = []
    replaced: set[UUID] = set()
    reconsiderations: dict[UUID, UUID] = {}
    merged_owners: dict[UUID, SourceCluster] = {}
    if allow_reconsideration:
        # A placeholder can block a DOI match. Use the alternate grouping only
        # for a reconsidered work and never split an existing identity component.
        original_groups = tuple(frozenset(cluster.item_ids) for cluster in combined)
        original_members = {item_id: group for group in original_groups for item_id in group}
        reconsideration_pool = cluster_discovery_items(
            items,
            include_provider_locations=True,
            require_identity=True,
            ignore_placeholder_titles=True,
        )
        absorbed: set[UUID] = set()
        for cluster in reconsideration_pool:
            member_ids = set(cluster.item_ids)
            frozen = {owned[item_id].cluster_id for item_id in member_ids if item_id in owned}
            if len(frozen) != 1 or any(
                not original_members[item_id] <= member_ids for item_id in member_ids
            ):
                continue
            owner = owned[next(item_id for item_id in cluster.item_ids if item_id in owned)]
            prior = tuple(item_id for item_id in owner.item_ids if item_id in scouted)
            if (
                not prior
                or any(scouted[item_id] != "skip" for item_id in prior)
                or not set(owner.item_ids) <= member_ids
            ):
                continue
            candidate = _reconsideration_candidate(
                screened=tuple(by_id[item_id] for item_id in prior),
                owner_items=tuple(by_id[item_id] for item_id in owner.item_ids),
                late=tuple(by_id[item_id] for item_id in cluster.item_ids if item_id not in owned),
            )
            if candidate is None:
                continue
            reconsiderations[candidate.item_id] = prior[0]
            absorbed.update(member_ids)
            covered.update(member_ids - {candidate.item_id})
            urls = {
                cluster.preferred_url,
                cluster.canonical_url,
                *cluster.alternate_urls,
                owner.preferred_url,
                owner.canonical_url,
                *owner.alternate_urls,
            }
            # Skipped owners have no capture to invalidate. Keep their work ID
            # and use the improved record's location first for ordinary capture.
            merged_owners[owner.cluster_id] = cluster.model_copy(
                update={
                    "cluster_id": owner.cluster_id,
                    "canonical_url": owner.canonical_url,
                    "preferred_url": candidate.source_url,
                    "alternate_urls": tuple(
                        sorted(urls - {owner.canonical_url, candidate.source_url})
                    ),
                }
            )
        combined = tuple(cluster for cluster in combined if cluster.item_ids[0] not in absorbed)
    for cluster in combined:
        frozen = {
            owned[item_id].cluster_id: owned[item_id]
            for item_id in cluster.item_ids
            if item_id in owned
        }
        if not frozen:
            late_clusters.append(cluster)
            continue
        late = tuple(by_id[item_id] for item_id in cluster.item_ids if item_id not in owned)
        if not late:
            continue
        # A late bridge cannot change two existing owners or confer Scout approval.
        if len(frozen) == 1:
            owner = next(iter(frozen.values()))
            prior = next((item_id for item_id in owner.item_ids if item_id in scouted), None)
            if prior is None and set(owner.item_ids) <= set(cluster.item_ids):
                # Unscreened work can use the richer cluster before it gains an owner.
                replaced.add(owner.cluster_id)
                late_clusters.append(cluster)
                continue
            if prior is not None:
                mirrors.extend(
                    V2LateDiscoveryMirror(item_id=item.item_id, scouted_item_id=prior)
                    for item in late
                )
        late_clusters.extend(
            cluster_discovery_items(late, include_provider_locations=True, require_identity=True)
        )
    owners = tuple(
        merged_owners.get(cluster.cluster_id, cluster)
        for cluster in prefix.clusters
        if cluster.cluster_id not in replaced
    )
    return (
        (*owners, *late_clusters),
        tuple(mirrors),
        frozenset(covered),
        reconsiderations,
    )


def _reconsideration_candidate(
    *,
    screened: tuple[NormalizedDiscoveryItem, ...],
    owner_items: tuple[NormalizedDiscoveryItem, ...],
    late: tuple[NormalizedDiscoveryItem, ...],
) -> NormalizedDiscoveryItem | None:
    titles = {_usable_reconsideration_title(item) for item in (*owner_items, *late)} - {""}
    if len(titles) > 1:
        return None
    had_title = any(_usable_reconsideration_title(item) for item in screened)
    screened_metadata = tuple(_scout_candidate(item, bounded=True) for item in screened)
    had_abstract = any(
        len(set(_title_key(item.abstract).split())) >= 12 for item in screened_metadata
    )
    prior_text = {_title_key(item.snippet) for item in screened_metadata}
    qualified = []
    for item in late:
        # Assess the text Scout can actually see and ignore a repeat of its snippet.
        abstract = _title_key(_scout_candidate(item, bounded=True).abstract)
        abstract_words = len(set(abstract.split()))
        has_abstract = abstract_words >= 12 and abstract not in prior_text
        has_title = bool(_usable_reconsideration_title(item))
        if (has_title and not had_title) or (has_abstract and not had_abstract):
            qualified.append(
                (
                    not has_abstract,
                    not has_title,
                    -abstract_words,
                    str(item.item_id),
                    item,
                )
            )
    return min(qualified)[-1] if qualified else None


def _usable_reconsideration_title(item: NormalizedDiscoveryItem) -> str:
    title = paper_title_key(item.title)
    if (
        is_placeholder_title(item.title)
        or is_placeholder_title(title)
        or title
        in {
            "n a",
            "no title",
            "no title available",
            "title unavailable",
            "untitled",
            "unknown",
            "unknown title",
        }
    ):
        return ""
    return title


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
    budget_snapshot: Callable[[], V2BudgetSnapshot] | None = None,
    downstream_input_tokens: Mapping[LLMStage, int] | None = None,
    target_gaps: tuple[str, ...] = (),
    on_batch: ScoutHandoff | None = None,
    first_pass_only: bool = False,
    first_pass: V2DiscoveryScoutRunResult | None = None,
) -> V2DiscoveryScoutRunResult:
    """Persist or resume one round of normalized discovery and batched Scout decisions."""
    suffix = "/first-pass-v1" if first_pass_only else ""
    output_key = _artifact_key(planner_output) + suffix
    ranking_key = _ranking_artifact_key(planner_output) + suffix
    prefix = first_pass.output if first_pass is not None else None
    prefix_batches = prefix.scout_batches if prefix is not None else ()
    prefix_audits = prefix.scout_audits if prefix is not None else ()
    prefix_scouted = frozenset(item.item_id for batch in prefix_batches for item in batch.items)
    now = clock or _utc_now
    completed_at = now()
    _require_aware(completed_at, "clock result")
    try:
        existing = read_v2_artifact(str(db_path), planner_output.run_id, output_key)
    except KeyError:
        existing = None
    if existing is not None:
        output = V2DiscoveryScoutOutput.model_validate_json(existing.payload_json)
        if output.directions != planner_output.directions:
            raise ValueError("persisted discovery output directions do not match the initial plan")
        return V2DiscoveryScoutRunResult(
            output=output,
            resumed=True,
            ranking_artifact=_read_ranking_artifact(db_path, planner_output, output, suffix=suffix),
        )
    routing_config.preflight()
    binding = _fresh_ranked_binding(db_path, planner_output.run_id)
    identity = binding.ranking_identity if binding is not None else None
    claim_aware = identity == RANKING_IDENTITY
    batch_size = V2_FRESH_SCOUT_BATCH_SIZE if claim_aware else V2_SCOUT_BATCH_SIZE
    exact_claim = binding.exact_claim if binding is not None and claim_aware else None
    scout_gaps = tuple(gap[:500] for gap in target_gaps[:6]) if claim_aware else ()
    prompt_path = _scout_prompt_path(identity)
    checkpoint_key = "scout-checkpoint-v1/" + output_key
    input_hash = checkpoint_hash(
        {
            "planner": planner_output.model_dump(mode="json"),
            "responses": [response.model_dump(mode="json") for response in responses],
            "binding": {
                "exact_claim": binding.exact_claim,
                "policy": binding.policy.model_dump(mode="json"),
                "ranking_identity": binding.ranking_identity,
            }
            if binding is not None
            else None,
            "routing": routing_config.preflight().model_dump(mode="json"),
            "prompt": load_prompt_file(prompt_path, expected_stage=LLMStage.SCOUT).sha256,
            **({"target_gaps": scout_gaps} if claim_aware else {}),
            **({"first_pass": prefix.model_dump(mode="json")} if prefix is not None else {}),
        }
    )
    checkpoint = read_checkpoint(
        str(db_path), planner_output.run_id, checkpoint_key, V2ScoutRoundCheckpoint
    )
    prior_ranking = None
    if checkpoint is None:
        reconsiderations: dict[UUID, UUID] = {}
        if binding is not None:
            try:
                prior_ranking = read_v2_artifact(str(db_path), planner_output.run_id, ranking_key)
            except KeyError:
                pass
            if prior_ranking is not None:
                completed_at = prior_ranking.created_at

        def resolve_nber(number: str) -> NberPaperMetadata | None:
            return _repair_nber_metadata(
                str(db_path), planner_output.run_id, number, now, cancellation_requested
            )

        delta = normalize_discovery_responses(
            run_id=planner_output.run_id,
            directions=planner_output.directions,
            responses=_without_prefix_results(responses, prefix)
            if prefix is not None
            else responses,
            discovered_at=completed_at,
            crossref_resolver=crossref_resolver,
            cancellation_requested=cancellation_requested,
            # Ranking-only historical checkpoints must reconstruct their original inputs.
            nber_resolver=resolve_nber if prior_ranking is None else None,
            url_identity_version=(
                2 if identity in {None, EXACT_URL_RANKING_IDENTITY, RANKING_IDENTITY} else 1
            ),
        )
        items = (*prefix.items, *delta) if prefix is not None else delta
        if prefix is not None:
            clusters, mirrors, covered, reconsiderations = _progressive_clusters(
                items,
                prefix,
                allow_reconsideration=claim_aware and prior_ranking is None,
            )
        else:
            clusters = cluster_discovery_items(
                items,
                include_provider_locations=binding is not None,
                require_identity=claim_aware,
            )
            mirrors, covered = (), frozenset()
        ranking_artifact: V2MetadataRankingArtifact | None = None
        scout_items = items
        if binding is not None:
            ranks = rank_metadata(
                items,
                exact_claim=binding.exact_claim,
                policy=binding.policy,
                ranking_identity=binding.ranking_identity,
                known_work_keys=_prior_work_keys(
                    db_path, planner_output.run_id, _round_number(planner_output)
                ),
                clustered_work_keys=_clustered_work_keys(items, clusters) if claim_aware else None,
                target_gaps=scout_gaps,
            )
            if prior_ranking is not None:
                ranking_artifact = V2MetadataRankingArtifact.model_validate_json(
                    prior_ranking.payload_json
                )
                if (
                    prior_ranking.artifact_type != "V2MetadataRankingArtifact"
                    or ranking_artifact.run_id != planner_output.run_id
                    or ranking_artifact.round_number != _round_number(planner_output)
                    or ranking_artifact.ranking_identity != binding.ranking_identity
                    or ranking_artifact.ranks != ranks
                    or ranking_artifact.identity_conflicts != _metadata_identity_conflicts(items)
                ):
                    raise ValueError("partial ranking checkpoint differs from its discovery input")
                selected = {
                    item.item_id
                    for item in ranking_artifact.scout_dispositions
                    if item.disposition == "scouted"
                }
                ordered = _scout_ids(ranks, binding.policy.max_scout_per_round, claim_aware)
                if not selected.issubset(ordered):
                    raise ValueError("partial ranking Scout selection exceeds its policy")
                by_id = {item.item_id: item for item in items}
                scout_items = tuple(by_id[item_id] for item_id in ordered if item_id in selected)
            else:
                scout_items, ranking_artifact = _ranked_scout_selection(
                    run_id=planner_output.run_id,
                    round_number=_round_number(planner_output),
                    directions=planner_output.directions,
                    items=items,
                    ranks=ranks,
                    policy=binding.policy,
                    ranking_identity=binding.ranking_identity,
                    routing_config=routing_config,
                    llm_provider=llm_provider,
                    budget_snapshot=budget_snapshot,
                    downstream_input_tokens=downstream_input_tokens,
                    exact_claim=exact_claim,
                    target_gaps=scout_gaps,
                    already_scouted=prefix_scouted,
                    excluded_items=covered | {link.item_id for link in mirrors},
                    reconsiderations=reconsiderations,
                    candidate_limit=_scout_tranche_limit(
                        binding.policy.max_scout_per_round,
                        first_pass_only,
                        len(prefix_batches),
                        batch_size,
                    ),
                    batch_offset=len(prefix_batches),
                )
        if prior_ranking is None:
            checkpoint = V2ScoutRoundCheckpoint(
                run_id=planner_output.run_id,
                policy=(
                    "scout-round-checkpoint-v2" if reconsiderations else "scout-round-checkpoint-v1"
                ),
                input_hash=input_hash,
                items=items,
                clusters=clusters,
                scout_item_ids=tuple(item.item_id for item in scout_items),
                ranking_artifact=ranking_artifact,
                created_at=completed_at,
            )
            insert_v2_artifact(str(db_path), checkpoint_key, checkpoint, completed_at)
    else:
        if checkpoint.input_hash != input_hash:
            raise ValueError("persisted Scout plan input identity changed")
        completed_at = checkpoint.created_at
        items, clusters = checkpoint.items, checkpoint.clusters
        for item in items:
            planner_output.directions.require_permitted(item.direction)
        if prefix is not None:
            expected_clusters, mirrors, _, reconsiderations = _progressive_clusters(
                items,
                prefix,
                allow_reconsideration=checkpoint.policy == "scout-round-checkpoint-v2",
            )
            saved_reconsiderations = (
                {
                    row.item_id: row.reconsidered_from_item_id
                    for row in checkpoint.ranking_artifact.scout_dispositions
                    if row.reconsidered_from_item_id is not None
                }
                if checkpoint.ranking_artifact is not None
                else {}
            )
            if reconsiderations != saved_reconsiderations:
                raise ValueError("persisted Scout reconsideration differs from its items")
        else:
            expected_clusters = cluster_discovery_items(
                items,
                include_provider_locations=binding is not None,
                require_identity=claim_aware,
            )
            mirrors = ()
        if clusters != expected_clusters:
            raise ValueError("persisted Scout clusters differ from their items")
        by_id = {item.item_id: item for item in items}
        scout_items = tuple(by_id[item_id] for item_id in checkpoint.scout_item_ids)
        ranking_artifact = checkpoint.ranking_artifact

    def publish_batch(
        batches: tuple[ScoutBatch, ...],
        audits: tuple[ScoutBatchAudit, ...],
        pending: tuple[LLMRequest, ...],
    ) -> None:
        if on_batch is not None and ranking_artifact is not None:
            on_batch(
                V2DiscoveryScoutOutput(
                    run_id=planner_output.run_id,
                    directions=planner_output.directions,
                    items=items,
                    clusters=clusters,
                    scout_batches=(*prefix_batches, *batches),
                    scout_audits=(*prefix_audits, *audits),
                    late_mirrors=mirrors,
                    completed_at=completed_at,
                ),
                ranking_artifact,
                pending,
                first_pass_only,
            )

    if prior_ranking is not None:
        # This formerly possible prefix was written after Scout, but did not save
        # its decisions. Physical-call records retain their original exposure.
        # The existing deterministic fallback is explicit; no completed call repeats.
        batches = tuple(
            ScoutBatch(
                run_id=planner_output.run_id,
                items=tuple(
                    ScoutItem(
                        item_id=item.item_id,
                        decision="maybe",
                        rationale="Scout decisions missing after interruption; ranking fallback.",
                    )
                    for item in scout_items[start : start + V2_SCOUT_BATCH_SIZE]
                ),
            )
            for start in range(0, len(scout_items), V2_SCOUT_BATCH_SIZE)
        )
        audits = tuple(
            ScoutBatchAudit(
                batch_number=index,
                attempted_calls=0,
                fallback_used=True,
                failure=(
                    "Legacy ranking-only checkpoint did not retain Scout decisions; "
                    "original physical-call charges/reservations remain in the run audit."
                ),
                recovery_policy="partial-ranking-recovery-v1",
            )
            for index in range(1, len(batches) + 1)
        )
    else:
        batches, audits = _run_scout_batches(
            run_id=planner_output.run_id,
            directions=planner_output.directions,
            items=scout_items,
            llm_provider=llm_provider,
            model_alias=routing_config.preflight().for_stage(LLMStage.SCOUT).logical_alias,
            clock=now,
            cancellation_requested=cancellation_requested,
            prompt_path=prompt_path,
            bounded_metadata=binding is not None,
            exact_claim=exact_claim,
            target_gaps=scout_gaps,
            db_path=str(db_path),
            checkpoint_key=checkpoint_key,
            on_batch=publish_batch if on_batch is not None else None,
            batch_offset=len(prefix_batches),
            batch_size=batch_size,
            max_workers=V2_SCOUT_MAX_WORKERS if claim_aware else 1,
        )
    output = V2DiscoveryScoutOutput(
        run_id=planner_output.run_id,
        directions=planner_output.directions,
        items=items,
        clusters=clusters,
        scout_batches=(*prefix_batches, *batches),
        scout_audits=(*prefix_audits, *audits),
        late_mirrors=mirrors,
        completed_at=completed_at,
    )
    artifacts = ((output_key, output, completed_at),)
    if ranking_artifact is not None:
        artifacts = (
            (ranking_key, ranking_artifact, completed_at),
            *artifacts,
        )
    insert_v2_artifact_batch(str(db_path), artifacts)
    return V2DiscoveryScoutRunResult(
        output=output, resumed=False, ranking_artifact=ranking_artifact
    )


def _without_prefix_results(
    responses: Sequence[V2DiscoveryResponse], prefix: V2DiscoveryScoutOutput
) -> tuple[V2DiscoveryResponse, ...]:
    prior = {item.item_id for item in prefix.items}
    remaining = set(prior)
    delta = []
    for response in responses:
        new = []
        for result in response.results:
            item_id = _item_id(prefix.run_id, response.query, result.rank, result.original_url)
            if item_id in prior:
                remaining.discard(item_id)
            else:
                new.append(result)
        if new:
            delta.append(V2DiscoveryResponse(query=response.query, results=tuple(new)))
    if remaining:
        raise ValueError("completed search lost a first-pass candidate")
    return tuple(delta)


def _raise_if_cancelled(callback: Callable[[], bool] | None) -> None:
    if callback is not None and callback():
        raise V2CancellationRequested("v2 cancellation was observed before discovery work")


def _fresh_ranked_binding(db_path: str | Path, run_id: UUID) -> V2DiscoveryBinding | None:
    try:
        binding = read_discovery_binding(str(db_path), run_id)
    except KeyError:
        return None
    if binding.compiler_identity == "source-query-compiler-v3":
        if binding.ranking_identity not in RANKING_IDENTITIES:
            raise ValueError("compiler v3 binding requires recognized metadata ranking")
        if not isinstance(binding.policy, V2MetadataDiscoveryPolicy):
            raise ValueError("compiler v3 binding requires the successor discovery policy")
        return binding
    return None


def uses_claim_ranking(db_path: str | Path, run_id: UUID) -> bool:
    binding = _fresh_ranked_binding(db_path, run_id)
    return binding is not None and binding.ranking_identity == RANKING_IDENTITY


def _round_number(planner_output: V2InitialPlannerOutput | V2AdaptiveRoundPlan) -> int:
    return 1 if isinstance(planner_output, V2InitialPlannerOutput) else planner_output.round_number


def _scout_prompt_path(ranking_identity: str | None) -> Traversable:
    if ranking_identity == RANKING_IDENTITY:
        return V2_SCOUT_V3_PROMPT_PATH
    return V2_SCOUT_V2_PROMPT_PATH if ranking_identity is not None else V2_SCOUT_PROMPT_PATH


def _scout_ids(ranks: tuple[MetadataRank, ...], limit: int, claim_aware: bool) -> tuple[UUID, ...]:
    if not claim_aware:
        return fair_ranked_ids(ranks, limit)
    by_work: dict[str, MetadataRank] = {}
    for rank in ranks:
        by_work.setdefault(rank.work_key, rank)
    strong, uncertain = [], []
    for rank in by_work.values():
        # Balance provider and direction coverage within each tier.
        if (rank.directness or 0) >= 0.6 and (rank.method_fit or 0) >= 0.8:
            strong.append(rank)
        else:
            uncertain.append(rank)
    first = fair_ranked_ids(strong, limit, highest_lane_first=True)
    return (
        *first,
        *fair_ranked_ids(uncertain, limit - len(first), highest_lane_first=True),
    )


def _scout_request(
    run_id: UUID,
    directions: ResearchDirections,
    batch_number: int,
    candidates: tuple[ScoutCandidate, ...],
    exact_claim: str | None,
    target_gaps: tuple[str, ...],
) -> V2ScoutRequest:
    if exact_claim is not None:
        return V2ClaimScoutRequest(
            run_id=run_id,
            directions=directions,
            batch_number=batch_number,
            candidates=candidates,
            exact_claim=exact_claim,
            target_gaps=target_gaps,
        )
    return V2ScoutRequest(
        run_id=run_id,
        directions=directions,
        batch_number=batch_number,
        candidates=candidates,
    )


def _selected_model_input_tokens(llm_provider: LLMProvider, request: LLMRequest) -> int:
    """Mirror the Budgeted provider's estimate, including selected adapter instructions."""
    minimum = conservative_token_estimate(request.rendered_prompt)
    estimator = getattr(llm_provider, "estimate_request_tokens", None)
    if callable(estimator):
        estimate = estimator(request)
    else:
        estimator = getattr(llm_provider, "conservative_input_tokens", None)
        if not callable(estimator):
            selected_provider = getattr(llm_provider, "_provider", llm_provider)
            estimator = getattr(selected_provider, "conservative_input_tokens", None)
        estimate = estimator(request, minimum) if callable(estimator) else minimum
    if isinstance(estimate, bool) or not isinstance(estimate, int) or estimate < minimum:
        raise ValueError(
            "selected Scout provider input estimate is invalid or below rendered prompt"
        )
    return estimate


def _scout_tranche_limit(
    cap: int, first_pass_only: bool, prefix_batches: int, batch_size: int
) -> int | None:
    if first_pass_only:
        return min(batch_size, max(1, cap // 2))
    if prefix_batches:
        batches = (cap + batch_size - 1) // batch_size
        return max(0, batches - prefix_batches) * batch_size
    return None


def _ranked_scout_selection(
    *,
    run_id: UUID,
    round_number: int,
    ranking_identity: str = "source-candidate-ranking-v2",
    directions: ResearchDirections,
    items: tuple[NormalizedDiscoveryItem, ...],
    ranks: tuple[MetadataRank, ...],
    policy: V2MetadataDiscoveryPolicy | V2DiscoveryPolicy,
    routing_config: V2RoutingConfig,
    llm_provider: LLMProvider,
    budget_snapshot: Callable[[], V2BudgetSnapshot] | None,
    downstream_input_tokens: Mapping[LLMStage, int] | None,
    exact_claim: str | None = None,
    target_gaps: tuple[str, ...] = (),
    already_scouted: frozenset[UUID] = frozenset(),
    excluded_items: frozenset[UUID] = frozenset(),
    reconsiderations: Mapping[UUID, UUID] | None = None,
    candidate_limit: int | None = None,
    batch_offset: int = 0,
) -> tuple[tuple[NormalizedDiscoveryItem, ...], V2MetadataRankingArtifact]:
    ranked_by_id = {item.item_id: item for item in ranks}
    by_item = {item.item_id: item for item in items}
    claim_aware = ranking_identity == RANKING_IDENTITY
    batch_size = V2_FRESH_SCOUT_BATCH_SIZE if claim_aware else V2_SCOUT_BATCH_SIZE
    available = policy.max_scout_per_round - len(already_scouted)
    if candidate_limit is not None:
        available = min(available, candidate_limit)
    ordered_ids = _scout_ids(
        tuple(rank for rank in ranks if rank.item_id not in excluded_items),
        available,
        claim_aware,
    )
    capped_items = tuple(ranked_by_id[item_id] for item_id in ordered_ids)
    snapshot_provider = budget_snapshot or getattr(llm_provider, "snapshot", None)
    safe_capacity = 0
    if callable(snapshot_provider):
        snapshot = snapshot_provider()
        route = routing_config.preflight()
        protected_inputs = downstream_input_tokens or {
            stage: 16_000 for stage, _stage_route in route.routing
        }
        prompt = load_prompt_file(
            _scout_prompt_path(ranking_identity), expected_stage=LLMStage.SCOUT
        )
        reservations = []
        for start in range(0, len(capped_items), batch_size):
            batch = capped_items[start : start + batch_size]
            request_input = _scout_request(
                run_id,
                directions,
                batch_offset + start // batch_size + 1,
                tuple(_scout_candidate(by_item[item.item_id], bounded=True) for item in batch),
                exact_claim,
                target_gaps,
            )
            rendered = render_stage_prompt(prompt, request_input, ScoutBatch)
            request = LLMRequest(
                run_id=run_id,
                stage=LLMStage.SCOUT,
                prompt=prompt,
                rendered_prompt=rendered,
                input_artifact=request_input,
                input_artifact_ids=(run_id,),
                requested_output_type=ScoutBatch,
                model_alias=route.for_stage(LLMStage.SCOUT).logical_alias,
                generation=V2_LLM_ROUTING.for_stage(LLMStage.SCOUT).generation,
            )
            estimate = _selected_model_input_tokens(llm_provider, request)
            reservation = route.reserve(LLMStage.SCOUT, estimate)
            # A malformed/truncated response can consume either complete attempt.
            reservations.extend((reservation, reservation))
        safe_attempts = safe_optional_model_prefix(
            snapshot=snapshot,
            routing=routing_config,
            downstream_input_tokens=protected_inputs,
            optional_reservations=tuple(reservations),
        )
        safe_capacity = min(
            policy.max_scout_per_round,
            (safe_attempts // 2) * batch_size,
            len(capped_items),
        )
    selected_ids = set(ordered_ids[:safe_capacity])
    capped_ids = {item.item_id for item in capped_items}
    selected = tuple(ranked_by_id[item_id] for item_id in ordered_ids if item_id in selected_ids)
    scout_items = tuple(by_item[rank.item_id] for rank in selected)
    selected_ids.update(already_scouted)
    dispositions = tuple(
        V2ScoutDisposition(
            item_id=rank.item_id,
            reconsidered_from_item_id=(reconsiderations or {}).get(rank.item_id),
            disposition=(
                "scouted"
                if rank.item_id in selected_ids
                else "not_scouted_budget"
                if rank.item_id in capped_ids
                else "not_scouted_cap"
            ),
        )
        for rank in ranks
    )
    artifact = V2MetadataRankingArtifact(
        run_id=run_id,
        ranking_identity=ranking_identity,
        round_number=round_number,
        ranks=ranks,
        scout_dispositions=dispositions,
        identity_conflicts=_metadata_identity_conflicts(items),
        retained_count=len(ranks),
        scouted_count=len(selected_ids),
        cap_limited_count=sum(item.disposition == "not_scouted_cap" for item in dispositions),
        budget_limited_count=sum(item.disposition == "not_scouted_budget" for item in dispositions),
    )
    return scout_items, artifact


def _metadata_identity_conflicts(
    items: tuple[NormalizedDiscoveryItem, ...],
) -> tuple[MetadataIdentityConflict, ...]:
    by_location: dict[str, list[tuple[UUID, str]]] = {}
    by_doi: dict[str, list[tuple[UUID, str]]] = {}
    for item in items:
        if not item.doi:
            continue
        try:
            doi = normalize_doi(item.doi)
        except ValueError:
            continue
        by_location.setdefault(item.canonical_url, []).append((item.item_id, doi))
        title = _title_key(item.title)
        if title:
            by_doi.setdefault(doi, []).append((item.item_id, title))

    conflicts: list[MetadataIdentityConflict] = []
    for entries in by_location.values():
        dois = {value for _item_id, value in entries}
        if len(dois) > 1:
            conflicts.append(
                MetadataIdentityConflict(
                    kind="same_location_distinct_doi",
                    item_ids=tuple(sorted({item_id for item_id, _value in entries}, key=str)),
                    values=tuple(_bounded_conflict_value(value) for value in sorted(dois)),
                )
            )
    for entries in by_doi.values():
        titles = {value for _item_id, value in entries}
        if len(titles) > 1:
            conflicts.append(
                MetadataIdentityConflict(
                    kind="same_doi_distinct_titles",
                    item_ids=tuple(sorted({item_id for item_id, _value in entries}, key=str)),
                    values=tuple(_bounded_conflict_value(value) for value in sorted(titles)),
                )
            )
    return tuple(
        sorted(
            conflicts,
            key=lambda item: (item.kind, item.values, tuple(map(str, item.item_ids))),
        )
    )


def _bounded_conflict_value(value: str) -> str:
    if len(value) <= 512:
        return value
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]
    return f"{value[:488]}…#{digest}"


def _ranking_artifact_key(
    planner_output: V2InitialPlannerOutput | V2AdaptiveRoundPlan,
) -> str:
    return f"{V2_RANKING_ARTIFACT_PREFIX}{_round_number(planner_output)}"


def _read_ranking_artifact(
    db_path: str | Path,
    planner_output: V2InitialPlannerOutput | V2AdaptiveRoundPlan,
    output: V2DiscoveryScoutOutput,
    *,
    suffix: str = "",
) -> V2MetadataRankingArtifact | None:
    if _fresh_ranked_binding(db_path, planner_output.run_id) is None:
        return None
    try:
        artifact = read_v2_artifact(
            str(db_path),
            planner_output.run_id,
            _ranking_artifact_key(planner_output) + suffix,
        )
    except KeyError as exc:
        raise ValueError("ranked discovery checkpoint is missing its ranking sidecar") from exc
    result = V2MetadataRankingArtifact.model_validate_json(artifact.payload_json)
    if result.run_id != planner_output.run_id or result.round_number != _round_number(
        planner_output
    ):
        raise ValueError("ranking sidecar does not match its discovery round")
    if {item.item_id for item in result.ranks} != {item.item_id for item in output.items}:
        raise ValueError("ranking sidecar membership differs from normalized discovery items")
    expected_scouted = {
        item.item_id for item in result.scout_dispositions if item.disposition == "scouted"
    }
    observed_scouted = {item.item_id for batch in output.scout_batches for item in batch.items}
    if expected_scouted != observed_scouted:
        raise ValueError("ranking sidecar Scout dispositions differ from completed batch inputs")
    return result


def _prior_work_keys(db_path: str | Path, run_id: UUID, round_number: int) -> tuple[str, ...]:
    keys: set[str] = set()
    for prior_round in range(1, round_number):
        sidecar_key = f"{V2_RANKING_ARTIFACT_PREFIX}{prior_round}"
        try:
            artifact = read_v2_artifact(str(db_path), run_id, sidecar_key)
        except KeyError:
            try:
                discovery = read_v2_artifact(
                    str(db_path), run_id, _round_discovery_artifact_key(prior_round)
                )
            except KeyError as exc:
                raise ValueError(
                    "later ranked discovery is missing an earlier discovery checkpoint"
                ) from exc
            if discovery.artifact_type != "V2DiscoveryScoutOutput":
                raise ValueError("prior discovery checkpoint has an unexpected type") from None
            empty = V2DiscoveryScoutOutput.model_validate_json(discovery.payload_json)
            if empty.run_id != run_id or any(
                (empty.items, empty.clusters, empty.scout_batches, empty.scout_audits)
            ):
                raise ValueError(
                    "nonempty prior discovery checkpoint is missing its ranking sidecar"
                ) from None
            continue
        if artifact.artifact_type != "V2MetadataRankingArtifact":
            raise ValueError("prior ranking artifact has an unexpected type")
        prior = V2MetadataRankingArtifact.model_validate_json(artifact.payload_json)
        if prior.run_id != run_id or prior.round_number != prior_round:
            raise ValueError("prior ranking sidecar belongs to another run or round")
        keys.update(rank.work_key for rank in prior.ranks)
    return tuple(sorted(keys))


def _round_discovery_artifact_key(round_number: int) -> str:
    if round_number == 1:
        return V2_SCOUT_ARTIFACT_KEY
    if round_number == 4:
        return "post-phase-13-round-4-discovery-scout-v1"
    return f"phase-7-round-{round_number}-discovery-scout"


def scout_ordered_item_ids(
    output: V2DiscoveryScoutOutput,
    ranks: tuple[MetadataRank, ...] | None = None,
) -> tuple[UUID, ...]:
    """Return retrieve/maybe candidates in deterministic provider-neutral fallback order."""
    decisions = {
        item.item_id: item.decision for batch in output.scout_batches for item in batch.items
    }
    order = {"retrieve": 0, "maybe": 1, "skip": 2}
    rank_by_id = {item.item_id: item.rank for item in ranks or ()}
    if ranks is not None:
        return tuple(
            item.item_id
            for item in sorted(
                output.items,
                key=lambda item: (
                    order.get(_decision_value(item.item_id, decisions), 3),
                    rank_by_id.get(item.item_id, 10**9),
                    item.canonical_url,
                    str(item.item_id),
                ),
            )
            if decisions.get(item.item_id) is None or decisions[item.item_id].value != "skip"
        )
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
    model_alias: ModelAlias,
    clock: Callable[[], datetime],
    cancellation_requested: Callable[[], bool] | None,
    prompt_path: Traversable = V2_SCOUT_PROMPT_PATH,
    bounded_metadata: bool = False,
    exact_claim: str | None = None,
    target_gaps: tuple[str, ...] = (),
    db_path: str | None = None,
    checkpoint_key: str | None = None,
    on_batch: Callable[
        [tuple[ScoutBatch, ...], tuple[ScoutBatchAudit, ...], tuple[LLMRequest, ...]],
        None,
    ]
    | None = None,
    batch_offset: int = 0,
    batch_size: int = V2_SCOUT_BATCH_SIZE,
    max_workers: int = 1,
) -> tuple[tuple[ScoutBatch, ...], tuple[ScoutBatchAudit, ...]]:
    _raise_if_cancelled(cancellation_requested)
    prompt = load_prompt_file(prompt_path, expected_stage=LLMStage.SCOUT)
    batches: list[ScoutBatch] = []
    audits: list[ScoutBatchAudit] = []
    requests = []
    for start in range(0, len(items), batch_size):
        batch_items = items[start : start + batch_size]
        request_input = _scout_request(
            run_id,
            directions,
            batch_offset + start // batch_size + 1,
            tuple(_scout_candidate(item, bounded=bounded_metadata) for item in batch_items),
            exact_claim,
            target_gaps,
        )
        requests.append(
            (
                request_input,
                LLMRequest(
                    run_id=run_id,
                    stage=LLMStage.SCOUT,
                    prompt=prompt,
                    rendered_prompt=render_stage_prompt(prompt, request_input, ScoutBatch),
                    input_artifact=request_input,
                    input_artifact_ids=(run_id,),
                    requested_output_type=ScoutBatch,
                    model_alias=model_alias,
                    generation=V2_LLM_ROUTING.for_stage(LLMStage.SCOUT).generation,
                ),
            )
        )
    stopped = Event()

    def cancelled() -> bool:
        return stopped.is_set() or bool(cancellation_requested and cancellation_requested())

    def run_batch(
        request_input: V2ScoutRequest, request: LLMRequest
    ) -> tuple[ScoutBatch, ScoutBatchAudit]:
        _raise_if_cancelled(cancelled)
        if prompt_path == V2_SCOUT_V3_PROMPT_PATH:
            first = (
                read_checkpoint(
                    db_path, run_id, f"{checkpoint_key}/batch-{request_input.batch_number}/attempt-1",
                    V2StageAttemptCheckpoint,
                )
                if db_path is not None and checkpoint_key is not None
                else None
            )
            if first is None or first.request_hash != stage_request_hash(request):
                compact = load_prompt_file(
                    prompt_resource("v2_scout_v4.md"), expected_stage=LLMStage.SCOUT
                )
                request = request.model_copy(update={
                    "prompt": compact,
                    "rendered_prompt": render_stage_prompt(compact, request_input, ScoutBatch),
                })
        last_error: LLMInvocationError | None = None
        response: ScoutBatch | None = None
        attempted = 0
        for number in range(1, 3):
            _raise_if_cancelled(cancelled)
            attempted += 1
            attempt = None
            saved = None
            if db_path is not None and checkpoint_key is not None:
                attempt, saved, _fresh = stage_attempt(
                    path=db_path,
                    key=f"{checkpoint_key}/batch-{request_input.batch_number}",
                    number=number,
                    request=request,
                    started_at=clock(),
                )
            if saved is not None:
                if saved.candidate is not None:
                    if not isinstance(saved.candidate, ScoutBatch):
                        raise ValueError("saved Scout outcome has the wrong output type")
                    _validate_scout_mapping(request_input, saved.candidate)
                    response = saved.candidate
                    break
                last_error = (
                    LLMInvocationError(saved.failure or "Scout failed", saved.invocation)
                    if saved.invocation is not None
                    else None
                )
                continue
            outcome = None
            try:
                current = (
                    request.model_copy(
                        update={
                            "input_artifact_ids": (
                                *request.input_artifact_ids,
                                attempt.attempt_id,
                            )
                        }
                    )
                    if attempt is not None
                    else request
                )
                invoked = invoke_llm(llm_provider, current, clock=clock)
                candidate = invoked.output_artifact
                if not isinstance(candidate, ScoutBatch):
                    raise ValueError("Scout returned an unexpected typed artifact")
                _validate_scout_mapping(request_input, candidate)
                response = candidate
                if attempt is not None:
                    outcome = V2StageOutcomeCheckpoint(
                        run_id=run_id,
                        attempt_id=attempt.attempt_id,
                        request_hash=attempt.request_hash,
                        candidate=candidate,
                        invocation=invoked.record,
                        completed_at=clock(),
                    )
            except V2CancellationRequested:
                raise
            except LLMInvocationError as exc:
                if isinstance(exc.__cause__, V2CancellationRequested):
                    raise exc.__cause__ from None
                last_error = exc
                if attempt is not None:
                    outcome = V2StageOutcomeCheckpoint(
                        run_id=run_id,
                        attempt_id=attempt.attempt_id,
                        request_hash=attempt.request_hash,
                        failure=str(exc),
                        invocation=exc.record,
                        completed_at=clock(),
                    )
            except ValueError:
                last_error = None
                if attempt is not None:
                    outcome = V2StageOutcomeCheckpoint(
                        run_id=run_id,
                        attempt_id=attempt.attempt_id,
                        request_hash=attempt.request_hash,
                        failure="Scout response mapping failed",
                        completed_at=clock(),
                    )
            if outcome is not None:
                assert db_path is not None and attempt is not None
                save_stage_outcome(db_path, attempt, outcome)
            if response is not None:
                break
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
            return response, ScoutBatchAudit(
                batch_number=request_input.batch_number,
                attempted_calls=attempted,
                fallback_used=True,
                failure=failure,
            )
        return response, ScoutBatchAudit(
            batch_number=request_input.batch_number, attempted_calls=attempted
        )

    def publish(index: int, result: tuple[ScoutBatch, ScoutBatchAudit]) -> None:
        response, audit = result
        batches.append(response)
        audits.append(audit)
        if on_batch is not None:
            on_batch(
                tuple(batches),
                tuple(audits),
                tuple(pending for _, pending in requests[index + 1 :]),
            )

    if max_workers == 1 or len(requests) <= 1:
        for index, (request_input, request) in enumerate(requests):
            publish(index, run_batch(request_input, request))
    else:
        write_scope = overlapping_database_writes(db_path) if db_path else nullcontext()
        with (
            write_scope,
            ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="scout-batch") as pool,
        ):
            futures = [
                pool.submit(copy_context().run, run_batch, request_input, request)
                for request_input, request in requests
            ]
            try:
                # Publish only complete prefixes so capture and replay keep deterministic ordering.
                for index, future in enumerate(futures):
                    publish(index, future.result())
            finally:
                stopped.set()
                for future in futures:
                    future.cancel()
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
    *,
    url_identity_version: Literal[1, 2] = 2,
) -> UUID:
    return uuid5(
        NAMESPACE_URL,
        f"researchassistant-v2-discovery::{run_id}::{query.query_id}::{rank}::"
        f"{canonical_discovery_url(url, version=url_identity_version)}",
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


def _normalized_doi(value: str | None, *, exact_identifiers: bool = False) -> str | None:
    if value is None:
        return None
    if exact_identifiers:
        try:
            return normalize_doi(value)
        except ValueError:
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
        if not resolved.verified:
            return CrossrefIdentityMetadata(
                doi=doi,
                verified=False,
                failure_code=resolved.failure_code or "UnverifiedIdentity",
            )
        if resolved.doi is None or normalize_doi(resolved.doi) != normalize_doi(doi):
            raise ValueError("Crossref work identifier differs from the requested DOI")
        return resolved.model_copy(update={"doi": normalize_doi(doi)})
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


def _provider_identity_anchors(item: NormalizedDiscoveryItem) -> set[tuple[str, str]]:
    if item.provider.value not in {"openalex", "arxiv", "pubmed"}:
        return set()
    anchors: set[tuple[str, str]] = set()
    for entry in item.provider_metadata:
        if entry.key == "external_id":
            try:
                value = json.loads(entry.value_json)
            except (json.JSONDecodeError, TypeError):
                continue
            if isinstance(value, str) and value:
                anchors.add((item.provider.value, value))
    return anchors


def _provider_full_text_locations(
    item: NormalizedDiscoveryItem, *, pdf_only: bool = False
) -> tuple[str, ...]:
    locations: set[str] = set()
    for entry in item.provider_metadata:
        if entry.key not in ({"pdf_url"} if pdf_only else {"pdf_url", "full_text_url"}):
            continue
        try:
            value = json.loads(entry.value_json)
        except (json.JSONDecodeError, TypeError):
            continue
        if not isinstance(value, str):
            continue
        try:
            safe_location(value)
            parsed = urlsplit(value)
            host = (parsed.hostname or "").rstrip(".").casefold()
            if (
                not host
                or any(character.isspace() for character in host)
                or host == "localhost"
                or host.endswith(
                    (
                        ".localhost",
                        ".local",
                        ".internal",
                        ".lan",
                        ".home",
                        ".test",
                        ".example",
                        ".invalid",
                    )
                )
            ):
                continue
            try:
                address = ipaddress.ip_address(host)
            except ValueError:
                address = None
                if all(character in "0123456789." for character in host):
                    continue
            if address is not None and not address.is_global:
                continue
            locations.add(canonical_discovery_url(value))
        except ValueError:
            continue
    return tuple(sorted(locations))


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


def _scout_candidate(item: NormalizedDiscoveryItem, *, bounded: bool = False) -> ScoutCandidate:
    def clip(value: str | None, limit: int) -> str | None:
        if value is None or not bounded:
            return value
        return value[:limit]

    return ScoutCandidate(
        item_id=item.item_id,
        direction=item.direction,
        title=clip(item.title, 400),
        source_url=clip(item.source_url, 2048) or item.source_url[:2048],
        snippet=clip(item.snippet, 800),
        abstract=clip(item.abstract, 2400),
        doi=clip(item.doi, 200),
        authors=tuple(author[:240] for author in item.authors[:12]) if bounded else item.authors,
        publication_date=clip(item.publication_date, 80),
        source_type=clip(item.source_type, 160),
    )


def _require_aware(value: datetime, name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")


def _utc_now() -> datetime:
    return datetime.now(UTC)
