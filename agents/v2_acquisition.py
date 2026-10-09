"""Fresh-v2 Phase-5 bounded acquisition, immutable snapshots, and deterministic Probe.

This module deliberately reuses the established scraper adapters.  It never reaches around
their URL, redirect, media-type, PDF, normalization, or Firecrawl fallback boundaries.
Probe is source-text prioritization only: it does not call an LLM or create evidence claims.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from datetime import UTC, datetime
from hashlib import sha256
from typing import Literal
from uuid import NAMESPACE_URL, UUID, uuid5

from pydantic import ConfigDict

from agents.v2_discovery import _provider_full_text_locations
from providers.acquisition import AcquisitionFailureCode
from providers.scraper import ScrapeRequest, ScrapeResponse, ScraperProvider, ScraperProviderError
from providers.v2_budget import V2CancellationRequested
from researchassistant.common.utils import count_words
from researchassistant.contracts.acquisition_ranking import (
    V2AcquisitionRankingAudit,
    V2ClusterAcquisitionDisposition,
)
from researchassistant.contracts.discovery_v2 import V2PreviewRequest, discovery_id
from researchassistant.contracts.metadata_ranking import V2MetadataRankingArtifact
from researchassistant.contracts.model_research import V2_CLAIM_PREVIEW_PROBE_POLICY_IDENTITY
from researchassistant.contracts.models import (
    V2_ACQUISITION_PROBE_LEGACY_POLICY_IDENTITY,
    V2_ACQUISITION_PROBE_POLICY_IDENTITY,
    ResearchDirection,
    SourceCluster,
    SourceSnapshot,
    StrictModel,
    V2AcquiredSource,
    V2AcquisitionAttempt,
    V2AcquisitionPolicy,
    V2AcquisitionProbeOutput,
    V2AcquisitionProvider,
    V2DiscoveryScoutOutput,
    V2ProbePassage,
    V2ProbeResult,
    V2SurvivingSource,
)
from researchassistant.evidence.evidence_core import (
    CURRENT_QUOTE_LENGTH_POLICY,
    build_source_snapshot,
    fresh_sentence_spans,
    has_statistical_markers,
)
from researchassistant.research.metadata_ranking import fair_ranked_ids
from researchassistant.research.source_preview import build_capture_windows, build_claim_preview
from researchassistant.storage.discovery_store import read_discovery_binding
from researchassistant.storage.query_retrieval_store import raw_hit_counts
from researchassistant.storage.store import insert_v2_artifact, read_v2_artifact

V2_ACQUISITION_PROBE_ARTIFACT_KEY = "phase-5-acquisition-probe"
_CONCLUSION_RE = re.compile(r"\b(conclusion|conclude|summary|in summary|overall|therefore)\b", re.I)
_CITATION_RE = re.compile(r"\[[0-9,;\- ]+\]|\b(references?|citations?)\b", re.I)
_NUMBER_RE = re.compile(r"\b\d+(?:\.\d+)?%?\b")
_URL_TEXT_RE = re.compile(r"(?:https?://|www\.)\S+", re.I)
_PAGE_CHROME_RE = re.compile(
    r"\b(?:skip to content|table of contents|cookie settings|sign in|log in|"
    r"next page|previous page|share this page|page\s+\d+\s+of\s+\d+|"
    r"click here to (?:read|view|continue)|contact us|about us|privacy policy|"
    r"terms of use|accessibility statement|all rights reserved|powered by)\b",
    re.I,
)
_PAGE_ERROR_RE = re.compile(
    r"\b(?:required part of (?:this|the) site (?:couldn[’']t|could not) load|"
    r"this may be due to a browser extension.{0,100}network issues.{0,100}browser settings|"
    r"error loading (?:the )?(?:page|site|content)|"
    r"failed to load (?:the )?(?:page|site|content)|"
    r"couldn[’']t load (?:the )?(?:page|site|content)|"
    r"please check your connection.{0,160}disable (?:any )?ad blockers.{0,160}"
    r"(?:try using|use) a different browser)\b",
    re.I,
)
_FALLBACK_FAILURE_CODES = frozenset(
    {
        AcquisitionFailureCode.WIGOLO_CONNECTION,
        AcquisitionFailureCode.WIGOLO_TIMEOUT,
        AcquisitionFailureCode.MALFORMED,
        AcquisitionFailureCode.EXTRACTION,
        AcquisitionFailureCode.CHALLENGE,
        AcquisitionFailureCode.AUTHENTICATION,
        AcquisitionFailureCode.PAYWALL,
    }
)


class V2AcquisitionProbeRunResult(StrictModel):
    """A small explicit return object without exposing mutable persistence internals."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    output: V2AcquisitionProbeOutput
    resumed: bool


class V2AcquisitionInputBinding(StrictModel):
    """Freeze all acquisition controls that affect a run before external reads begin."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: UUID
    round_number: int
    discovery_sha256: str
    policy: V2AcquisitionPolicy
    exact_claim: str | None
    asserted_components: tuple[str, ...]
    target_gaps: tuple[str, ...]
    excluded_cluster_ids: tuple[UUID, ...]


def run_v2_acquisition_probe(
    *,
    db_path: str,
    discovery_output: V2DiscoveryScoutOutput,
    wigolo_provider: ScraperProvider | None,
    firecrawl_provider: ScraperProvider | None = None,
    policy: V2AcquisitionPolicy | None = None,
    exact_claim: str | None = None,
    asserted_components: tuple[str, ...] = (),
    target_gaps: tuple[str, ...] = (),
    excluded_cluster_ids: frozenset[UUID] = frozenset(),
    cancellation_requested: Callable[[], bool] | None = None,
    clock: Callable[[], datetime] | None = None,
) -> V2AcquisitionProbeRunResult:
    """Acquire ordered Scout candidates once, snapshot them, Probe them, and persist audit data."""
    now = clock or _utc_now
    policy = policy or V2AcquisitionPolicy()
    if policy.policy_identity == V2_CLAIM_PREVIEW_PROBE_POLICY_IDENTITY and not exact_claim:
        raise ValueError("claim-aware acquisition requires the frozen exact claim")
    completed_at = now()
    _require_aware(completed_at, "clock result")
    round_number = _discovery_round(discovery_output)
    artifact_key = (
        V2_ACQUISITION_PROBE_ARTIFACT_KEY
        if round_number == 1
        else "post-phase-13-round-4-acquisition-probe-v1"
        if round_number == 4
        else f"phase-7-round-{round_number}-acquisition-probe"
    )
    binding_key = f"{artifact_key}-input-binding"
    binding = V2AcquisitionInputBinding(
        run_id=discovery_output.run_id,
        round_number=round_number,
        discovery_sha256=sha256(discovery_output.model_dump_json().encode("utf-8")).hexdigest(),
        policy=policy,
        exact_claim=exact_claim,
        asserted_components=asserted_components,
        target_gaps=target_gaps,
        excluded_cluster_ids=tuple(sorted(excluded_cluster_ids, key=str)),
    )
    try:
        existing = read_v2_artifact(db_path, discovery_output.run_id, artifact_key)
    except KeyError:
        existing = None
    try:
        existing_binding = read_v2_artifact(db_path, discovery_output.run_id, binding_key)
    except KeyError:
        existing_binding = None
    if existing_binding is not None:
        stored_binding = V2AcquisitionInputBinding.model_validate_json(
            existing_binding.payload_json
        )
        if stored_binding != binding:
            raise ValueError("persisted acquisition input identity changed; use a new run")
    if existing is not None:
        output = V2AcquisitionProbeOutput.model_validate_json(existing.payload_json)
        if policy.policy_identity == V2_CLAIM_PREVIEW_PROBE_POLICY_IDENTITY:
            if output.policy_identity != policy.policy_identity or any(
                probe.preview is None
                or probe.preview.request.exact_claim != exact_claim
                or probe.preview.request.asserted_components != asserted_components
                or probe.preview.request.target_gaps != target_gaps
                for probe in output.probes
            ):
                raise ValueError("claim-aware acquisition identity changed; use a new run")
        if output.directions != discovery_output.directions:
            raise ValueError("persisted acquisition output directions do not match Scout output")
        return V2AcquisitionProbeRunResult(output=output, resumed=True)
    if existing_binding is None:
        insert_v2_artifact(db_path, binding_key, binding, completed_at)

    decisions = {
        item.item_id: item.decision.value
        for batch in discovery_output.scout_batches
        for item in batch.items
    }
    item_by_id = {item.item_id: item for item in discovery_output.items}
    ordered_clusters = sorted(
        discovery_output.clusters,
        key=lambda cluster: _cluster_order(cluster, item_by_id, decisions),
    )
    ranking: V2MetadataRankingArtifact | None = None
    try:
        binding = read_discovery_binding(db_path, discovery_output.run_id)
    except KeyError:
        binding = None
    if binding is not None and binding.compiler_identity == "source-query-compiler-v3":
        ranking = V2MetadataRankingArtifact.model_validate_json(
            read_v2_artifact(
                db_path, discovery_output.run_id, f"phase-3-metadata-ranking-round-{round_number}"
            ).payload_json
        )
        if (
            ranking.run_id != discovery_output.run_id
            or ranking.round_number != round_number
            or {item.item_id for item in ranking.ranks} != set(item_by_id)
        ):
            raise ValueError("acquisition ranking sidecar differs from its discovery pool")
        eligible = sorted(
            (
                rank
                for rank in ranking.ranks
                if decisions.get(rank.item_id) in {"retrieve", "maybe"}
            ),
            key=lambda rank: ({"retrieve": 0, "maybe": 1}[decisions[rank.item_id]], rank.rank),
        )
        eligible = tuple(
            rank.model_copy(update={"rank": index}) for index, rank in enumerate(eligible, 1)
        )
        candidate_ids = fair_ranked_ids(eligible, len(eligible))
        cluster_by_item = {
            item_id: cluster
            for cluster in discovery_output.clusters
            for item_id in cluster.item_ids
        }
        chosen_clusters = []
        chosen_ids = set()
        for item_id in candidate_ids:
            cluster = cluster_by_item[item_id]
            if cluster.cluster_id in chosen_ids or cluster.cluster_id in excluded_cluster_ids:
                continue
            chosen_ids.add(cluster.cluster_id)
            chosen_clusters.append(cluster)
        direction_target = getattr(binding.policy, "sources_per_direction_per_round", None)
        if direction_target is not None:
            direction_counts: dict[ResearchDirection, int] = {}
            bounded_clusters: list[SourceCluster] = []
            for cluster in chosen_clusters:
                direction = _cluster_direction(cluster, item_by_id, decisions)
                if direction is None or direction_counts.get(direction, 0) >= direction_target:
                    continue
                direction_counts[direction] = direction_counts.get(direction, 0) + 1
                bounded_clusters.append(cluster)
            chosen_clusters = bounded_clusters
        ordered_clusters = chosen_clusters[
            : min(policy.max_clusters, binding.policy.max_acquisition_per_round)
        ]
    attempts: list[V2AcquisitionAttempt] = []
    acquired: list[V2AcquiredSource] = []
    probes: list[V2ProbeResult] = []
    survivors: list[V2SurvivingSource] = []
    acquired_urls: set[str] = set()
    duplicate_cluster_ids: set[UUID] = set()

    for cluster in ordered_clusters[: policy.max_clusters]:
        _raise_if_cancelled(cancellation_requested)
        if cluster.cluster_id in excluded_cluster_ids:
            continue
        direction = _cluster_direction(cluster, item_by_id, decisions)
        if direction is None:
            # Scout skip remains an audit-preserved discovery decision, not an acquisition.
            continue
        if {cluster.preferred_url, cluster.canonical_url, *cluster.alternate_urls} & acquired_urls:
            duplicate_cluster_ids.add(cluster.cluster_id)
            continue
        source, cluster_attempts = _acquire_cluster(
            run_id=discovery_output.run_id,
            cluster=cluster,
            direction=direction,
            primary=wigolo_provider,
            fallback=firecrawl_provider,
            policy=policy,
            retrieved_at=completed_at,
            cancellation_requested=cancellation_requested,
            preferred_locations=tuple(
                dict.fromkeys(
                    url
                    for item_id in cluster.item_ids
                    for url in _provider_full_text_locations(item_by_id[item_id], pdf_only=True)
                    if url in {cluster.preferred_url, *cluster.alternate_urls}
                )
            )
            if ranking is not None
            else (),
        )
        attempts.extend(cluster_attempts)
        if source is None:
            continue
        acquired_urls.update(
            {
                cluster.preferred_url,
                cluster.canonical_url,
                *cluster.alternate_urls,
                source.snapshot.source_url,
            }
        )
        acquired.append(source)
        try:
            if policy.policy_identity == V2_ACQUISITION_PROBE_LEGACY_POLICY_IDENTITY:
                probe = probe_snapshot(
                    snapshot=source.snapshot,
                    cluster_id=cluster.cluster_id,
                    policy_identity=policy.policy_identity,
                )
            else:
                probe = probe_snapshot(
                    snapshot=source.snapshot,
                    cluster_id=cluster.cluster_id,
                )
        except Exception as exc:
            probe = V2ProbeResult(
                cluster_id=cluster.cluster_id,
                snapshot_id=source.snapshot.snapshot_id,
                snapshot_sha256=source.snapshot.snapshot_sha256,
                succeeded=False,
                failure=f"{type(exc).__name__}: {exc}"[:500],
            )
        if policy.policy_identity == V2_CLAIM_PREVIEW_PROBE_POLICY_IDENTITY:
            key = f"acquisition-preview/{cluster.cluster_id}/{source.snapshot.snapshot_id}"
            request = V2PreviewRequest(
                run_id=discovery_output.run_id,
                artifact_id=discovery_id(discovery_output.run_id, "V2PreviewRequest", key),
                identity_key=key,
                exact_claim=exact_claim,
                direction=direction,
                directions=discovery_output.directions,
                source_id=cluster.cluster_id,
                snapshot_id=source.snapshot.snapshot_id,
                snapshot_hash=source.snapshot.snapshot_sha256,
                preview_identity="source-claim-preview-v2",
                asserted_components=asserted_components,
                target_gaps=target_gaps,
            )
            preview = build_claim_preview(request, source.snapshot)
            if not preview.capture_usable:
                probe = V2ProbeResult(
                    cluster_id=cluster.cluster_id,
                    snapshot_id=source.snapshot.snapshot_id,
                    snapshot_sha256=source.snapshot.snapshot_sha256,
                    succeeded=False,
                    failure=preview.reason,
                    preview=preview,
                )
            else:
                capture_spans = build_capture_windows(source.snapshot)
                capture_text = " ".join(span.text for span in capture_spans)
                minimum_words = (
                    CURRENT_QUOTE_LENGTH_POLICY.statistical_min_words
                    if has_statistical_markers(capture_text)
                    else CURRENT_QUOTE_LENGTH_POLICY.non_statistical_min_words
                )
                useful = bool(capture_spans) and count_words(capture_text) >= minimum_words
                selected = preview.spans if preview.outcome == "completed" else capture_spans
                probe = V2ProbeResult(
                    cluster_id=cluster.cluster_id,
                    snapshot_id=source.snapshot.snapshot_id,
                    snapshot_sha256=source.snapshot.snapshot_sha256,
                    succeeded=useful,
                    failure=None
                    if useful
                    else "acquired snapshot cannot meet the minimum quote length",
                    preview=preview,
                    passages=tuple(
                        V2ProbePassage(
                            passage_id=str(
                                uuid5(
                                    NAMESPACE_URL,
                                    f"researchassistant-v2-probe-v3::{source.snapshot.snapshot_id}::{span.start}::{span.end}",
                                )
                            ),
                            snapshot_id=source.snapshot.snapshot_id,
                            snapshot_sha256=source.snapshot.snapshot_sha256,
                            source_cluster_id=cluster.cluster_id,
                            start_char=span.start,
                            end_char=span.end,
                            text=span.text,
                            score=preview.relevance_score,
                            signals=span.relevance_signals,
                        )
                        for span in selected
                    )
                    if useful
                    else (),
                )
        probes.append(probe)
        if probe.succeeded and probe.passages:
            survivors.append(
                V2SurvivingSource(
                    cluster_id=cluster.cluster_id,
                    direction=direction,
                    snapshot_id=source.snapshot.snapshot_id,
                    snapshot_sha256=source.snapshot.snapshot_sha256,
                    passage_ids=tuple(passage.passage_id for passage in probe.passages),
                )
            )
    output = V2AcquisitionProbeOutput(
        run_id=discovery_output.run_id,
        directions=discovery_output.directions,
        acquisitions=tuple(acquired),
        attempts=tuple(attempts),
        probes=tuple(probes),
        survivors=tuple(survivors),
        policy_identity=policy.policy_identity,
        completed_at=completed_at,
    )
    if ranking is not None:
        shortlisted = {item.cluster_id for item in ordered_clusters}
        fetched = {item.cluster_id for item in acquired}
        usable = {item.cluster_id for item in survivors}
        dispositions = tuple(
            V2ClusterAcquisitionDisposition(
                cluster_id=cluster.cluster_id,
                shortlisted=cluster.cluster_id in shortlisted,
                disposition="usable"
                if cluster.cluster_id in usable
                else "fetched_unusable"
                if cluster.cluster_id in fetched
                else "duplicate"
                if cluster.cluster_id in duplicate_cluster_ids
                else "unavailable"
                if cluster.cluster_id in shortlisted
                else "excluded_prior"
                if cluster.cluster_id in excluded_cluster_ids
                else "not_scouted"
                if not any(item_id in decisions for item_id in cluster.item_ids)
                else "scout_skipped"
                if not any(
                    decisions.get(item_id) in {"retrieve", "maybe"} for item_id in cluster.item_ids
                )
                else "cap_prevented",
            )
            for cluster in discovery_output.clusters
        )
        audit = V2AcquisitionRankingAudit(
            run_id=discovery_output.run_id,
            round_number=round_number,
            raw_hits=raw_hit_counts(db_path, discovery_output.run_id).get(round_number, 0),
            deduplicated_works=len(discovery_output.clusters),
            scouted_candidates=len(decisions),
            acquisition_shortlisted_clusters=len(shortlisted),
            fetched_documents=len(acquired),
            usable_survivors=len(survivors),
            dispositions=dispositions,
        )
        insert_v2_artifact(
            db_path, f"metadata-acquisition-v2-round-{round_number}", audit, completed_at
        )
    insert_v2_artifact(db_path, artifact_key, output, completed_at)
    return V2AcquisitionProbeRunResult(output=output, resumed=False)


def _discovery_round(output: V2DiscoveryScoutOutput) -> int:
    rounds = {item.round_number for item in output.items}
    if not rounds:
        raise ValueError("v2 discovery output requires at least one item")
    if len(rounds) != 1:
        raise ValueError("v2 discovery output cannot mix research rounds")
    round_number = rounds.pop()
    if round_number < 1 or round_number > 4:
        raise ValueError("v2 acquisition permits only research rounds 1 through 4")
    return round_number


def probe_snapshot(
    *,
    snapshot: SourceSnapshot,
    cluster_id: UUID,
    policy_identity: Literal[
        "researchassistant-v2-phase-5-acquisition-probe-v1",
        "researchassistant-v2-phase-5-acquisition-probe-v2",
    ] = V2_ACQUISITION_PROBE_POLICY_IDENTITY,
) -> V2ProbeResult:
    """Return two to five exact, cheaply ranked snapshot passages when text permits."""
    if policy_identity not in {
        V2_ACQUISITION_PROBE_LEGACY_POLICY_IDENTITY,
        V2_ACQUISITION_PROBE_POLICY_IDENTITY,
    }:
        raise ValueError("unsupported v2 acquisition Probe policy identity")
    spans = fresh_sentence_spans(snapshot.normalized_text)
    if not spans:
        return V2ProbeResult(
            cluster_id=cluster_id,
            snapshot_id=snapshot.snapshot_id,
            snapshot_sha256=snapshot.snapshot_sha256,
            succeeded=policy_identity == V2_ACQUISITION_PROBE_LEGACY_POLICY_IDENTITY,
            failure=(
                None
                if policy_identity == V2_ACQUISITION_PROBE_LEGACY_POLICY_IDENTITY
                else "acquired snapshot has no selectable sentences"
            ),
        )
    candidates = [
        (score, start, end, text, signals)
        for index, (start, end, text) in enumerate(
            (span.start_char, span.end_char, span.text) for span in spans
        )
        for score, signals in (_passage_score(text=text, index=index, total=len(spans)),)
    ]
    substantive_candidates = [
        item
        for item in candidates
        if _is_substantive_passage(item[3], policy_identity=policy_identity)
    ]
    if substantive_candidates:
        candidates = substantive_candidates
    elif policy_identity != V2_ACQUISITION_PROBE_LEGACY_POLICY_IDENTITY:
        return V2ProbeResult(
            cluster_id=cluster_id,
            snapshot_id=snapshot.snapshot_id,
            snapshot_sha256=snapshot.snapshot_sha256,
            succeeded=False,
            failure="acquired snapshot contains no substantive passages",
        )
    if policy_identity == V2_ACQUISITION_PROBE_POLICY_IDENTITY:
        quoteable_text = " ".join(item[3] for item in substantive_candidates)
        minimum_words = (
            CURRENT_QUOTE_LENGTH_POLICY.statistical_min_words
            if has_statistical_markers(quoteable_text)
            else CURRENT_QUOTE_LENGTH_POLICY.non_statistical_min_words
        )
        if count_words(quoteable_text) < minimum_words:
            return V2ProbeResult(
                cluster_id=cluster_id,
                snapshot_id=snapshot.snapshot_id,
                snapshot_sha256=snapshot.snapshot_sha256,
                succeeded=False,
                failure="acquired snapshot cannot meet the minimum quote length",
            )
    candidates.sort(key=lambda item: (-item[0], item[1], item[2]))
    selected = sorted(candidates[: min(5, len(candidates))], key=lambda item: item[1])
    passages = tuple(
        V2ProbePassage(
            passage_id=str(
                uuid5(
                    NAMESPACE_URL,
                    f"researchassistant-v2-probe::{snapshot.snapshot_id}::{start}::{end}",
                )
            ),
            snapshot_id=snapshot.snapshot_id,
            snapshot_sha256=snapshot.snapshot_sha256,
            source_cluster_id=cluster_id,
            start_char=start,
            end_char=end,
            text=text,
            score=score,
            signals=signals,
        )
        for score, start, end, text, signals in selected
    )
    return V2ProbeResult(
        cluster_id=cluster_id,
        snapshot_id=snapshot.snapshot_id,
        snapshot_sha256=snapshot.snapshot_sha256,
        succeeded=True,
        passages=passages,
    )


def _acquire_cluster(
    *,
    run_id: UUID,
    cluster: SourceCluster,
    direction: ResearchDirection,
    primary: ScraperProvider | None,
    fallback: ScraperProvider | None,
    policy: V2AcquisitionPolicy,
    retrieved_at: datetime,
    cancellation_requested: Callable[[], bool] | None,
    preferred_locations: tuple[str, ...] = (),
) -> tuple[V2AcquiredSource | None, tuple[V2AcquisitionAttempt, ...]]:
    attempts: list[V2AcquisitionAttempt] = []
    urls = tuple(
        dict.fromkeys((*preferred_locations, cluster.preferred_url, *cluster.alternate_urls))
    )[: policy.max_urls_per_cluster]
    for url in urls:
        _raise_if_cancelled(cancellation_requested)
        response: ScrapeResponse | None = None
        primary_error: ScraperProviderError | None = None
        if primary is None:
            attempts.append(
                _failed_attempt(
                    cluster.cluster_id,
                    url,
                    V2AcquisitionProvider.WIGOLO,
                    "unavailable",
                    "Wigolo is unavailable",
                )
            )
        else:
            try:
                _raise_if_cancelled(cancellation_requested)
                response = primary.scrape(
                    ScrapeRequest(url=url, timeout_seconds=policy.timeout_seconds)
                )
                _require_response(response)
                attempts.append(
                    _successful_attempt(cluster.cluster_id, url, V2AcquisitionProvider.WIGOLO)
                )
            except ScraperProviderError as exc:
                response = None
                primary_error = exc
                attempts.append(
                    _failed_attempt(
                        cluster.cluster_id,
                        url,
                        V2AcquisitionProvider.WIGOLO,
                        exc.code,
                        str(exc) or exc.code,
                    )
                )
            except Exception as exc:
                response = None
                attempts.append(
                    _failed_attempt(
                        cluster.cluster_id,
                        url,
                        V2AcquisitionProvider.WIGOLO,
                        type(exc).__name__,
                        str(exc) or "Wigolo acquisition failed",
                    )
                )
        if response is None and _can_fallback(primary_error, fallback, policy):
            try:
                _raise_if_cancelled(cancellation_requested)
                response = fallback.scrape(  # type: ignore[union-attr]
                    ScrapeRequest(
                        url=url,
                        timeout_seconds=policy.timeout_seconds,
                        verified_preflight=primary_error.verified_preflight,
                    )
                )
                _require_response(response)
                attempts.append(
                    _successful_attempt(cluster.cluster_id, url, V2AcquisitionProvider.FIRECRAWL)
                )
            except ScraperProviderError as exc:
                response = None
                attempts.append(
                    _failed_attempt(
                        cluster.cluster_id,
                        url,
                        V2AcquisitionProvider.FIRECRAWL,
                        exc.code,
                        str(exc) or exc.code,
                    )
                )
            except Exception as exc:
                response = None
                attempts.append(
                    _failed_attempt(
                        cluster.cluster_id,
                        url,
                        V2AcquisitionProvider.FIRECRAWL,
                        type(exc).__name__,
                        str(exc) or "Firecrawl acquisition failed",
                    )
                )
        if response is not None:
            snapshot = _snapshot_from_response(run_id, cluster, url, response, retrieved_at)
            return (
                V2AcquiredSource(
                    cluster_id=cluster.cluster_id,
                    direction=direction,
                    snapshot=snapshot,
                    provider=(
                        V2AcquisitionProvider.FIRECRAWL
                        if attempts[-1].provider is V2AcquisitionProvider.FIRECRAWL
                        else V2AcquisitionProvider.WIGOLO
                    ),
                ),
                tuple(attempts),
            )
    return None, tuple(attempts)


def _raise_if_cancelled(callback: Callable[[], bool] | None) -> None:
    if callback is not None and callback():
        raise V2CancellationRequested("v2 cancellation was observed before acquisition work")


def _snapshot_from_response(
    run_id: UUID,
    cluster: SourceCluster,
    requested_url: str,
    response: ScrapeResponse,
    retrieved_at: datetime,
) -> SourceSnapshot:
    if not response.text.strip():
        raise ValueError("acquisition returned empty normalized text")
    snapshot_id = uuid5(
        NAMESPACE_URL,
        "researchassistant-v2-snapshot::"
        f"{run_id}::{cluster.cluster_id}::{response.resolved_url}::"
        f"{response.snapshot_sha256 or response.text}",
    )
    return build_source_snapshot(
        run_id=run_id,
        retrieval_attempt_id=uuid5(
            NAMESPACE_URL,
            f"researchassistant-v2-retrieval::{run_id}::{cluster.cluster_id}::{requested_url}",
        ),
        snapshot_id=snapshot_id,
        source_url=response.resolved_url,
        original_url=response.original_url or requested_url,
        canonical_url=response.canonical_url,
        retrieved_at=retrieved_at,
        normalized_text=response.text,
        truncated=response.truncated,
        normalization_version=response.normalization_version,
        acquisition_version=response.acquisition_version,
        provider_name=response.provider_name,
        provider_version=response.provider_version,
        media_type_provenance=response.media_type_provenance,
        created_at=retrieved_at,
    )


def _cluster_order(
    cluster: SourceCluster, item_by_id: dict[UUID, object], decisions: dict[UUID, str]
) -> tuple[int, int, str]:
    decision_order = {"retrieve": 0, "maybe": 1, "skip": 2}
    members = [item_by_id[item_id] for item_id in cluster.item_ids]
    return (
        min(decision_order.get(decisions.get(member.item_id, "skip"), 2) for member in members),
        min(member.provider_rank for member in members),
        cluster.canonical_url,
    )


def _cluster_direction(
    cluster: SourceCluster, item_by_id: dict[UUID, object], decisions: dict[UUID, str]
) -> ResearchDirection | None:
    ranked = sorted(
        (item_by_id[item_id] for item_id in cluster.item_ids),
        key=lambda item: (
            {"retrieve": 0, "maybe": 1, "skip": 2}.get(decisions.get(item.item_id, "skip"), 2),
            item.provider_rank,
            str(item.item_id),
        ),
    )
    if not ranked or decisions.get(ranked[0].item_id, "skip") == "skip":
        return None
    return ranked[0].direction


def _can_fallback(
    error: ScraperProviderError | None,
    fallback: ScraperProvider | None,
    policy: V2AcquisitionPolicy,
) -> bool:
    return bool(
        policy.allow_firecrawl_fallback
        and fallback is not None
        and error is not None
        and error.code in _FALLBACK_FAILURE_CODES
        and error.verified_preflight is not None
    )


def _is_substantive_passage(text: str, *, policy_identity: str) -> bool:
    if _PAGE_CHROME_RE.search(text):
        return False
    if policy_identity == V2_ACQUISITION_PROBE_POLICY_IDENTITY and _PAGE_ERROR_RE.search(text):
        return False
    without_urls = _URL_TEXT_RE.sub(" ", text)
    words = re.findall(r"\b[\w'-]+\b", without_urls)
    if len(words) < 5:
        return False
    if re.fullmatch(
        r"\s*(?:home|menu|search|print|close|back|next|previous)\s*[.!]?\s*", text, re.I
    ):
        return False
    return any(character.isalpha() for character in without_urls)


def _passage_score(*, text: str, index: int, total: int) -> tuple[int, tuple[str, ...]]:
    signals: list[str] = ["opening" if index < 2 else "body"]
    score = 1
    if index >= max(0, total - 2) or _CONCLUSION_RE.search(text):
        score += 3
        signals.append("conclusion")
    if _NUMBER_RE.search(text):
        score += 2
        signals.append("numeric")
    if _CITATION_RE.search(text):
        score += 2
        signals.append("citation")
    score += min(3, len(text.split()) // 20)
    return score, tuple(signals)


def _successful_attempt(
    cluster_id: UUID, url: str, provider: V2AcquisitionProvider
) -> V2AcquisitionAttempt:
    return V2AcquisitionAttempt(cluster_id=cluster_id, url=url, provider=provider, succeeded=True)


def _failed_attempt(
    cluster_id: UUID, url: str, provider: V2AcquisitionProvider, code: str, message: str
) -> V2AcquisitionAttempt:
    return V2AcquisitionAttempt(
        cluster_id=cluster_id,
        url=url,
        provider=provider,
        succeeded=False,
        failure_code=code,
        failure_message=message,
    )


def _require_response(response: ScrapeResponse) -> None:
    if not isinstance(response, ScrapeResponse):
        raise TypeError("acquisition provider returned a non-ScrapeResponse value")
    if not response.text.strip():
        raise ScraperProviderError("empty_capture", "acquisition returned empty normalized text")


def _require_aware(value: datetime, name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")


def _utc_now() -> datetime:
    return datetime.now(UTC)
