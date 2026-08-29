"""Fresh-v2 Phase-5 bounded acquisition, immutable snapshots, and deterministic Probe.

This module deliberately reuses the established scraper adapters.  It never reaches around
their URL, redirect, media-type, PDF, normalization, or Firecrawl fallback boundaries.
Probe is source-text prioritization only: it does not call an LLM or create evidence claims.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from datetime import UTC, datetime
from uuid import NAMESPACE_URL, UUID, uuid5

from pydantic import ConfigDict

from agents.researcher import build_source_snapshot
from models import (
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
from providers.acquisition import AcquisitionFailureCode
from providers.scraper import ScrapeRequest, ScrapeResponse, ScraperProvider, ScraperProviderError
from providers.v2_budget import V2CancellationRequested
from store import insert_v2_artifact, read_v2_artifact

V2_ACQUISITION_PROBE_ARTIFACT_KEY = "phase-5-acquisition-probe"
_SENTENCE_RE = re.compile(r"[^.!?\n]+(?:[.!?]+|$)", re.DOTALL)
_CONCLUSION_RE = re.compile(r"\b(conclusion|conclude|summary|in summary|overall|therefore)\b", re.I)
_CITATION_RE = re.compile(r"\[[0-9,;\- ]+\]|\b(references?|citations?)\b", re.I)
_NUMBER_RE = re.compile(r"\b\d+(?:\.\d+)?%?\b")
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


def run_v2_acquisition_probe(
    *,
    db_path: str,
    discovery_output: V2DiscoveryScoutOutput,
    wigolo_provider: ScraperProvider | None,
    firecrawl_provider: ScraperProvider | None = None,
    policy: V2AcquisitionPolicy | None = None,
    excluded_cluster_ids: frozenset[UUID] = frozenset(),
    cancellation_requested: Callable[[], bool] | None = None,
    clock: Callable[[], datetime] | None = None,
) -> V2AcquisitionProbeRunResult:
    """Acquire ordered Scout candidates once, snapshot them, Probe them, and persist audit data."""
    now = clock or _utc_now
    policy = policy or V2AcquisitionPolicy()
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
    try:
        existing = read_v2_artifact(db_path, discovery_output.run_id, artifact_key)
    except KeyError:
        existing = None
    if existing is not None:
        output = V2AcquisitionProbeOutput.model_validate_json(existing.payload_json)
        if output.directions != discovery_output.directions:
            raise ValueError("persisted acquisition output directions do not match Scout output")
        return V2AcquisitionProbeRunResult(output=output, resumed=True)

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
    attempts: list[V2AcquisitionAttempt] = []
    acquired: list[V2AcquiredSource] = []
    probes: list[V2ProbeResult] = []
    survivors: list[V2SurvivingSource] = []
    acquired_urls: set[str] = set()

    for cluster in ordered_clusters[: policy.max_clusters]:
        _raise_if_cancelled(cancellation_requested)
        if cluster.cluster_id in excluded_cluster_ids:
            continue
        direction = _cluster_direction(cluster, item_by_id, decisions)
        if direction is None:
            # Scout skip remains an audit-preserved discovery decision, not an acquisition.
            continue
        if {cluster.preferred_url, cluster.canonical_url, *cluster.alternate_urls} & acquired_urls:
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
        completed_at=completed_at,
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


def probe_snapshot(*, snapshot: SourceSnapshot, cluster_id: UUID) -> V2ProbeResult:
    """Return two to five exact, cheaply ranked snapshot passages when text permits."""
    spans = _sentence_spans(snapshot.normalized_text)
    if not spans:
        return V2ProbeResult(
            cluster_id=cluster_id,
            snapshot_id=snapshot.snapshot_id,
            snapshot_sha256=snapshot.snapshot_sha256,
            succeeded=True,
        )
    candidates = [
        (score, start, end, text, signals)
        for index, (start, end, text) in enumerate(spans)
        for score, signals in (_passage_score(text=text, index=index, total=len(spans)),)
    ]
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
) -> tuple[V2AcquiredSource | None, tuple[V2AcquisitionAttempt, ...]]:
    attempts: list[V2AcquisitionAttempt] = []
    urls = (cluster.preferred_url, *cluster.alternate_urls)[: policy.max_urls_per_cluster]
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


def _sentence_spans(text: str) -> tuple[tuple[int, int, str], ...]:
    spans: list[tuple[int, int, str]] = []
    for match in _SENTENCE_RE.finditer(text):
        start, end = match.span()
        while start < end and text[start].isspace():
            start += 1
        while end > start and text[end - 1].isspace():
            end -= 1
        if start < end:
            spans.append((start, end, text[start:end]))
    return tuple(spans)


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


def _require_aware(value: datetime, name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")


def _utc_now() -> datetime:
    return datetime.now(UTC)
