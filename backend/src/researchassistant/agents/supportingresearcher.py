"""Deterministic Phase 7B retrieval shared by both researcher stances."""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from threading import Event, Lock
from typing import Literal
from uuid import NAMESPACE_URL, UUID, uuid5

from pydantic import Field, model_validator

from researchassistant.common.utils import compute_sha256
from researchassistant.contracts.discovery_ranking import DiscoveryDecision
from researchassistant.contracts.models import (
    ClaimDefinition,
    PlannerOutput,
    ProvisionalCandidate,
    RetrievalRecord,
    RetrievalStatus,
    SearchQuery,
    SourceSnapshot,
    Stance,
    StrictModel,
    VerbatimQuoteSelection,
    missing_required_query_exclusions,
)
from researchassistant.contracts.retrieval import ATTEMPTS_PER_STANCE as ATTEMPTS_PER_STANCE
from researchassistant.contracts.retrieval import QUERIES_PER_STANCE as QUERIES_PER_STANCE
from researchassistant.contracts.retrieval import RESULTS_PER_QUERY as RESULTS_PER_QUERY
from researchassistant.contracts.retrieval import (
    ResearcherRetrievalBatch as ResearcherRetrievalBatch,
)
from researchassistant.contracts.retrieval import RetrievalOutcome as RetrievalOutcome
from researchassistant.contracts.scraping import (
    RetryPolicy,
    ScrapeRequest,
    ScrapeResponse,
    ScrapeStatus,
)
from researchassistant.contracts.search import (
    SearchFailureCode,
    SearchRequest,
    SearchResponse,
    SearchResult,
)
from researchassistant.evidence.evidence_core import (
    UNTRUSTED_SOURCE_INSTRUCTION_POLICY,  # noqa: F401
    UNTRUSTED_SOURCE_LABEL,  # noqa: F401
    UntrustedSourceText,
    assemble_quote_block_from_selected_segments,
    build_source_snapshot,
    numbered_source_text,
    validate_snapshot_integrity,
)
from researchassistant.evidence.evidence_portfolio import identify_source_family
from researchassistant.providers.ranking import rank_acquired_sources, rank_discovery_pool
from researchassistant.providers.scraper import (
    ScraperProvider,
    ScraperProviderError,
    ScraperTimeoutError,
)
from researchassistant.providers.search import SearchProvider, SearchProviderError

TOTAL_INTENDED_ATTEMPTS = ATTEMPTS_PER_STANCE * 2
SNAPSHOT_WORD_LIMIT = 3_000
_WORD_RE = re.compile(r"[A-Za-z0-9]+(?:[-'][A-Za-z0-9]+)*(?:%)?")


class AcquisitionPolicy(StrictModel):
    """Bounded rank/keep policy for one Researcher query."""

    discovery_results_per_query: int = Field(default=3, ge=3, le=100)
    usable_snapshots_per_query: int = Field(default=3, ge=1, le=10)
    source_target_per_stance: Literal[5, 7, 10, 15, 20] | None = None

    @model_validator(mode="after")
    def validate_keep_limit(self) -> AcquisitionPolicy:
        if self.usable_snapshots_per_query > self.discovery_results_per_query:
            raise ValueError("usable snapshot target cannot exceed discovery depth")
        return self

    @property
    def maximum_attempts_per_stance(self) -> int:
        if self.source_target_per_stance is not None:
            # Keep five ranked fallbacks available for acquisition or exact-quote
            # failure while retaining a hard per-stance work bound.
            return min(25, self.source_target_per_stance + 5)
        return self.discovery_results_per_query * QUERIES_PER_STANCE


MVP3A_ACQUISITION_POLICY = AcquisitionPolicy(
    discovery_results_per_query=5,
    usable_snapshots_per_query=3,
)


class CooperativeCancellation(RuntimeError):
    """Shared signal that provider-boundary code must never normalize as a provider error."""


class ExtractionLLMInput(StrictModel):
    """Typed extraction input; source content cannot carry application instructions."""

    run_id: UUID
    stance: Stance
    claim_definition: ClaimDefinition
    source: UntrustedSourceText
    selectable_source_text: str = ""
    retrieval: RetrievalRecord | None = None

    @model_validator(mode="after")
    def validate_run(self) -> ExtractionLLMInput:
        if self.claim_definition.run_id != self.run_id:
            raise ValueError("claim definition run_id must match extraction run_id")
        if self.retrieval is not None:
            if self.retrieval.run_id != self.run_id:
                raise ValueError("retrieval run_id must match extraction run_id")
        if not self.selectable_source_text:
            self.selectable_source_text = numbered_source_text(self.source.text)
        return self


def build_extraction_llm_input(
    *,
    planner: PlannerOutput,
    snapshot: SourceSnapshot,
    stance: Stance,
    retrieval: RetrievalRecord | None = None,
) -> ExtractionLLMInput:
    """Wrap immutable snapshot text in the required explicit untrusted-data envelope."""
    if snapshot.run_id != planner.run_id:
        raise ValueError("snapshot run_id must match Planner output")
    if retrieval is not None:
        if retrieval.run_id != planner.run_id:
            raise ValueError("retrieval run_id must match Planner output")
        if retrieval.retrieval_attempt_id != snapshot.retrieval_attempt_id:
            raise ValueError("retrieval attempt must match the snapshot")
        if retrieval.resolved_url != snapshot.source_url:
            raise ValueError("retrieval resolved URL must match the snapshot source URL")
    validate_snapshot_integrity(snapshot)
    return ExtractionLLMInput(
        run_id=planner.run_id,
        stance=stance,
        claim_definition=planner.claim_definition,
        source=UntrustedSourceText(
            snapshot_id=snapshot.snapshot_id,
            snapshot_sha256=snapshot.snapshot_sha256,
            text=snapshot.normalized_text,
            truncated=snapshot.truncated,
        ),
        selectable_source_text=numbered_source_text(snapshot.normalized_text),
        retrieval=retrieval,
    )


def build_provisional_candidate_from_selection(
    extraction_input: ExtractionLLMInput,
    selection: VerbatimQuoteSelection,
    *,
    extraction_prompt_version: str,
    extraction_model_name: str,
    extracted_at: datetime,
) -> ProvisionalCandidate:
    """Assemble the persisted legacy-compatible candidate from a semantic selection."""
    retrieval = extraction_input.retrieval
    if retrieval is None:
        raise ValueError("quote selection requires retrieval-backed extraction input")
    return ProvisionalCandidate(
        run_id=extraction_input.run_id,
        stance=extraction_input.stance,
        source_url=retrieval.resolved_url,
        retrieval_attempt_id=retrieval.retrieval_attempt_id,
        query_id=retrieval.query_id,
        query_round=retrieval.query_round,
        search_rank=retrieval.search_rank,
        snapshot_id=extraction_input.source.snapshot_id,
        snapshot_sha256=extraction_input.source.snapshot_sha256,
        extracted_quote_block=assemble_quote_block_from_selected_segments(
            extraction_input.source.text,
            selection,
            truncated=extraction_input.source.truncated,
        ),
        extraction_prompt_version=extraction_prompt_version,
        extraction_model_name=extraction_model_name,
        extracted_at=extracted_at,
    )


class BalancedRetrievalResult(StrictModel):
    run_id: UUID
    intended_attempt_count: Literal[18] = TOTAL_INTENDED_ATTEMPTS
    supporting: ResearcherRetrievalBatch
    opposing: ResearcherRetrievalBatch

    @model_validator(mode="after")
    def validate_balance(self) -> BalancedRetrievalResult:
        if self.supporting.run_id != self.run_id or self.opposing.run_id != self.run_id:
            raise ValueError("both researcher batches must match the run ID")
        if self.supporting.stance is not Stance.SUPPORTING:
            raise ValueError("supporting batch has the wrong stance")
        if self.opposing.stance is not Stance.OPPOSING:
            raise ValueError("opposing batch has the wrong stance")
        if self.supporting.intended_attempt_count != self.opposing.intended_attempt_count:
            raise ValueError("supporting and opposing retrieval depth must be equal")
        return self


@dataclass
class DeduplicationState:
    original_urls: dict[str, UUID] = field(default_factory=dict)
    resolved_urls: dict[str, UUID] = field(default_factory=dict)
    content_hashes: dict[str, UUID] = field(default_factory=dict)
    source_families: dict[UUID, UUID] = field(default_factory=dict)
    resolved_by_original: dict[str, str] = field(default_factory=dict)
    in_flight_original_urls: dict[str, Event] = field(default_factory=dict)
    lock: Lock = field(default_factory=Lock, repr=False)


Clock = Callable[[], datetime]
SnapshotConsumer = Callable[[SourceSnapshot], None]


def retrieve_supporting(
    planner: PlannerOutput,
    search_provider: SearchProvider,
    scraper_provider: ScraperProvider,
    *,
    retry_policy: RetryPolicy | None = None,
    acquisition_policy: AcquisitionPolicy | None = None,
    clock: Clock | None = None,
    snapshot_consumer: SnapshotConsumer | None = None,
    boundary_check: Callable[[], None] | None = None,
    deduplication: DeduplicationState | None = None,
) -> ResearcherRetrievalBatch:
    """Retrieve the three supporting rounds at a fixed depth of three."""
    return _retrieve_stance(
        planner,
        Stance.SUPPORTING,
        search_provider,
        scraper_provider,
        retry_policy=retry_policy or RetryPolicy(),
        acquisition_policy=acquisition_policy or AcquisitionPolicy(),
        clock=clock or _utc_now,
        deduplication=deduplication or DeduplicationState(),
        snapshot_consumer=snapshot_consumer,
        boundary_check=boundary_check,
    )


def retrieve_balanced(
    planner: PlannerOutput,
    search_provider: SearchProvider,
    scraper_provider: ScraperProvider,
    *,
    retry_policy: RetryPolicy | None = None,
    acquisition_policy: AcquisitionPolicy | None = None,
    clock: Clock | None = None,
    snapshot_consumer: SnapshotConsumer | None = None,
    boundary_check: Callable[[], None] | None = None,
) -> BalancedRetrievalResult:
    """Retrieve both sides with one shared deduplication boundary."""
    policy = retry_policy or RetryPolicy()
    acquisition = acquisition_policy or AcquisitionPolicy()
    now = clock or _utc_now
    deduplication = DeduplicationState()
    supporting = _retrieve_stance(
        planner,
        Stance.SUPPORTING,
        search_provider,
        scraper_provider,
        retry_policy=policy,
        acquisition_policy=acquisition,
        clock=now,
        deduplication=deduplication,
        snapshot_consumer=snapshot_consumer,
        boundary_check=boundary_check,
    )
    opposing = _retrieve_stance(
        planner,
        Stance.OPPOSING,
        search_provider,
        scraper_provider,
        retry_policy=policy,
        acquisition_policy=acquisition,
        clock=now,
        deduplication=deduplication,
        snapshot_consumer=snapshot_consumer,
        boundary_check=boundary_check,
    )
    return BalancedRetrievalResult(
        run_id=planner.run_id,
        supporting=supporting,
        opposing=opposing,
    )


def _retrieve_stance(
    planner: PlannerOutput,
    stance: Stance,
    search_provider: SearchProvider,
    scraper_provider: ScraperProvider,
    *,
    retry_policy: RetryPolicy,
    acquisition_policy: AcquisitionPolicy,
    clock: Clock,
    deduplication: DeduplicationState,
    snapshot_consumer: SnapshotConsumer | None,
    boundary_check: Callable[[], None] | None,
) -> ResearcherRetrievalBatch:
    queries = _queries_for_stance(planner, stance)
    if acquisition_policy.source_target_per_stance is not None:
        return _retrieve_ranked_stance(
            planner,
            stance,
            queries,
            search_provider,
            scraper_provider,
            retry_policy=retry_policy,
            acquisition_policy=acquisition_policy,
            clock=clock,
            deduplication=deduplication,
            snapshot_consumer=snapshot_consumer,
            boundary_check=boundary_check,
        )
    outcomes: list[RetrievalOutcome] = []
    snapshots: list[SourceSnapshot] = []

    for query in queries:
        request = SearchRequest(
            query_text=_query_with_exclusions(query),
            limit=acquisition_policy.discovery_results_per_query,
        )
        if boundary_check is not None:
            boundary_check()
        try:
            response = search_provider.search(request)
        except CooperativeCancellation:
            raise
        except SearchProviderError:
            raise
        except Exception as exc:
            raise SearchProviderError(
                f"search failed for {stance.value} round {query.query_round}: {exc}"
            ) from exc
        if boundary_check is not None:
            boundary_check()
        if not isinstance(response, SearchResponse):
            raise SearchProviderError("search provider returned a non-SearchResponse value")
        if not response.results:
            raise SearchProviderError(
                SearchFailureCode.EMPTY_RESULTS,
                "search returned no discovery results",
                retryable=False,
            )

        usable_for_query = 0
        for rank, result in enumerate(
            response.results[: acquisition_policy.discovery_results_per_query],
            start=1,
        ):
            outcome, snapshot = _retrieve_result(
                planner.run_id,
                query,
                rank,
                result.original_url,
                scraper_provider,
                retry_policy,
                clock,
                deduplication,
                boundary_check,
            )
            outcomes.append(outcome)
            if snapshot is not None:
                snapshots.append(snapshot)
                usable_for_query += 1
                if snapshot_consumer is not None:
                    snapshot_consumer(snapshot)
                if usable_for_query >= acquisition_policy.usable_snapshots_per_query:
                    break

    return ResearcherRetrievalBatch(
        run_id=planner.run_id,
        stance=stance,
        intended_attempt_count=acquisition_policy.maximum_attempts_per_stance,
        discovery_results_per_query=acquisition_policy.discovery_results_per_query,
        usable_snapshots_per_query=acquisition_policy.usable_snapshots_per_query,
        outcomes=outcomes,
        snapshots=snapshots,
    )


def _retrieve_ranked_stance(
    planner: PlannerOutput,
    stance: Stance,
    queries: list[SearchQuery],
    search_provider: SearchProvider,
    scraper_provider: ScraperProvider,
    *,
    retry_policy: RetryPolicy,
    acquisition_policy: AcquisitionPolicy,
    clock: Clock,
    deduplication: DeduplicationState,
    snapshot_consumer: SnapshotConsumer | None,
    boundary_check: Callable[[], None] | None,
) -> ResearcherRetrievalBatch:
    source_target = acquisition_policy.source_target_per_stance
    if source_target is None:
        raise ValueError("ranked retrieval requires a source target")
    query_results: list[tuple[SearchQuery, SearchResult]] = []
    for query in queries:
        request = SearchRequest(
            run_id=planner.run_id,
            provider=query.provider,
            intent=query.intent,
            query_text=_query_with_exclusions(query),
            limit=acquisition_policy.discovery_results_per_query,
        )
        if boundary_check is not None:
            boundary_check()
        response = search_provider.search(request)
        if boundary_check is not None:
            boundary_check()
        if not isinstance(response, SearchResponse):
            raise SearchProviderError("search provider returned a non-SearchResponse value")
        if not response.results:
            if response.degraded_pool:
                continue
            raise SearchProviderError(
                SearchFailureCode.EMPTY_RESULTS,
                f"{query.provider.value} returned no discovery results",
                retryable=False,
            )
        query_results.extend((query, result) for result in response.results)
    if not query_results:
        raise SearchProviderError(
            SearchFailureCode.EMPTY_RESULTS,
            f"no discovery results remained for the {stance.value} pool",
            retryable=False,
        )
    ranking = rank_discovery_pool(
        claim_text=planner.claim_definition.claim_text,
        claim_facets=_ranking_facets(planner.claim_definition),
        query_results=tuple(query_results),
        source_target=source_target,
    )
    eligible = [item for item in ranking if item.decision is not DiscoveryDecision.DISCARDED]
    outcomes: list[RetrievalOutcome] = []
    snapshots: list[SourceSnapshot] = []
    for acquisition_rank, item in enumerate(
        eligible[: acquisition_policy.maximum_attempts_per_stance],
        start=1,
    ):
        outcome, snapshot = _retrieve_result(
            planner.run_id,
            item.query,
            acquisition_rank,
            item.result.original_url,
            scraper_provider,
            retry_policy,
            clock,
            deduplication,
            boundary_check,
        )
        outcomes.append(outcome)
        if snapshot is not None:
            snapshots.append(snapshot)
            if snapshot_consumer is not None:
                snapshot_consumer(snapshot)
    acquired_ranking = rank_acquired_sources(
        claim_text=planner.claim_definition.claim_text,
        claim_facets=_ranking_facets(planner.claim_definition),
        snapshots=tuple(snapshots),
        retrievals=tuple(outcome.retrieval for outcome in outcomes),
    )
    snapshot_by_id = {snapshot.snapshot_id: snapshot for snapshot in snapshots}
    snapshots = [snapshot_by_id[item.snapshot_id] for item in acquired_ranking]
    return ResearcherRetrievalBatch(
        run_id=planner.run_id,
        stance=stance,
        intended_attempt_count=acquisition_policy.maximum_attempts_per_stance,
        discovery_results_per_query=acquisition_policy.discovery_results_per_query,
        usable_snapshots_per_query=acquisition_policy.usable_snapshots_per_query,
        source_target_per_stance=source_target,
        discovery_ranking=ranking,
        acquired_source_ranking=acquired_ranking,
        outcomes=outcomes,
        snapshots=snapshots,
    )


def _ranking_facets(claim_definition: ClaimDefinition) -> tuple[str, ...]:
    """Pass only optional Planner scope facets to the soft deterministic ranker."""
    return (
        claim_definition.population,
        claim_definition.intervention_or_exposure,
        claim_definition.causal_or_comparative_meaning,
    )


def _retrieve_result(
    run_id: UUID,
    query: SearchQuery,
    rank: int,
    original_url: str,
    scraper_provider: ScraperProvider,
    retry_policy: RetryPolicy,
    clock: Clock,
    deduplication: DeduplicationState,
    boundary_check: Callable[[], None] | None,
) -> tuple[RetrievalOutcome, SourceSnapshot | None]:
    retrieval_attempt_id = uuid5(
        NAMESPACE_URL,
        f"phase-7b-retrieval::{run_id}::{query.query_id}::{rank}::{original_url}",
    )
    while True:
        if boundary_check is not None:
            boundary_check()
        with deduplication.lock:
            snapshot_id = deduplication.original_urls.get(original_url)
            resolved_url = deduplication.resolved_by_original.get(original_url)
            if snapshot_id is not None and resolved_url is not None:
                owner_event = None
                wait_event = None
            else:
                wait_event = deduplication.in_flight_original_urls.get(original_url)
                if wait_event is None:
                    owner_event = Event()
                    deduplication.in_flight_original_urls[original_url] = owner_event
                else:
                    owner_event = None
        if snapshot_id is not None and resolved_url is not None:
            return _duplicate_original_url_outcome(
                run_id,
                query,
                rank,
                original_url,
                resolved_url,
                snapshot_id,
                retrieval_attempt_id,
                clock,
            )
        if owner_event is not None:
            break
        if wait_event is None:
            raise RuntimeError("URL in-flight coordination lost its event")
        while not wait_event.wait(timeout=0.05):
            if boundary_check is not None:
                boundary_check()

    try:
        return _retrieve_result_claimed(
            run_id,
            query,
            rank,
            original_url,
            scraper_provider,
            retry_policy,
            clock,
            deduplication,
            boundary_check,
        )
    finally:
        with deduplication.lock:
            if deduplication.in_flight_original_urls.get(original_url) is owner_event:
                del deduplication.in_flight_original_urls[original_url]
            owner_event.set()


def _duplicate_original_url_outcome(
    run_id: UUID,
    query: SearchQuery,
    rank: int,
    original_url: str,
    resolved_url: str,
    snapshot_id: UUID,
    retrieval_attempt_id: UUID,
    clock: Clock,
) -> tuple[RetrievalOutcome, None]:
    record = _retrieval_record(
        run_id,
        retrieval_attempt_id,
        query,
        rank,
        original_url,
        resolved_url,
        RetrievalStatus.SKIPPED,
        clock(),
    )
    return (
        RetrievalOutcome(
            retrieval=record,
            scrape_status=ScrapeStatus.DUPLICATE_URL,
            attempts_made=0,
            duplicate_of_snapshot_id=snapshot_id,
        ),
        None,
    )


def _retrieve_result_claimed(
    run_id: UUID,
    query: SearchQuery,
    rank: int,
    original_url: str,
    scraper_provider: ScraperProvider,
    retry_policy: RetryPolicy,
    clock: Clock,
    deduplication: DeduplicationState,
    boundary_check: Callable[[], None] | None,
) -> tuple[RetrievalOutcome, SourceSnapshot | None]:
    retrieval_attempt_id = uuid5(
        NAMESPACE_URL,
        f"phase-7b-retrieval::{run_id}::{query.query_id}::{rank}::{original_url}",
    )
    with deduplication.lock:
        snapshot_id = deduplication.original_urls.get(original_url)
        resolved_url = deduplication.resolved_by_original.get(original_url)
    if snapshot_id is not None and resolved_url is not None:
        record = _retrieval_record(
            run_id,
            retrieval_attempt_id,
            query,
            rank,
            original_url,
            resolved_url,
            RetrievalStatus.SKIPPED,
            clock(),
        )
        return (
            RetrievalOutcome(
                retrieval=record,
                scrape_status=ScrapeStatus.DUPLICATE_URL,
                attempts_made=0,
                duplicate_of_snapshot_id=snapshot_id,
            ),
            None,
        )

    response, failure_status, failure_code, failure_message, attempts_made = _scrape_with_retry(
        scraper_provider,
        original_url,
        retry_policy,
        boundary_check,
    )
    retrieved_at = clock()
    if response is None:
        if failure_status is ScrapeStatus.UNSUPPORTED:
            record = _retrieval_record(
                run_id,
                retrieval_attempt_id,
                query,
                rank,
                original_url,
                original_url,
                RetrievalStatus.SKIPPED,
                retrieved_at,
            )
            return (
                RetrievalOutcome(
                    retrieval=record,
                    scrape_status=ScrapeStatus.UNSUPPORTED,
                    content_type="application/octet-stream",
                    attempts_made=attempts_made,
                    failure_code=failure_code,
                ),
                None,
            )
        record = _retrieval_record(
            run_id,
            retrieval_attempt_id,
            query,
            rank,
            original_url,
            original_url,
            RetrievalStatus.FAILED,
            retrieved_at,
        )
        return (
            RetrievalOutcome(
                retrieval=record,
                scrape_status=failure_status,
                attempts_made=attempts_made,
                failure_code=failure_code,
                failure_message=failure_message,
            ),
            None,
        )

    content_type = _normalized_content_type(response.content_type)
    normalized_pdf = (
        content_type == "application/pdf" and response.normalization_version is not None
    )
    if not _is_supported_content_type(content_type) or (
        content_type == "application/pdf" and not normalized_pdf
    ):
        record = _retrieval_record(
            run_id,
            retrieval_attempt_id,
            query,
            rank,
            original_url,
            response.resolved_url,
            RetrievalStatus.SKIPPED,
            retrieved_at,
        )
        return (
            RetrievalOutcome(
                retrieval=record,
                scrape_status=ScrapeStatus.UNSUPPORTED,
                content_type=content_type,
                provider_name=response.provider_name,
                provider_version=response.provider_version,
                canonical_url=response.canonical_url,
                normalization_version=response.normalization_version,
                acquisition_version=response.acquisition_version,
                media_type_provenance=response.media_type_provenance,
                attempts_made=attempts_made,
                failure_code="unsupported_content",
            ),
            None,
        )

    with deduplication.lock:
        snapshot_id = deduplication.resolved_urls.get(response.resolved_url)
        if snapshot_id is not None:
            deduplication.original_urls[original_url] = snapshot_id
            deduplication.resolved_by_original[original_url] = response.resolved_url
    if snapshot_id is not None:
        record = _retrieval_record(
            run_id,
            retrieval_attempt_id,
            query,
            rank,
            original_url,
            response.resolved_url,
            RetrievalStatus.SKIPPED,
            retrieved_at,
        )
        return (
            RetrievalOutcome(
                retrieval=record,
                scrape_status=ScrapeStatus.DUPLICATE_URL,
                content_type=content_type,
                attempts_made=attempts_made,
                duplicate_of_snapshot_id=snapshot_id,
            ),
            None,
        )

    if response.normalization_version is not None:
        normalized_text = response.text
        truncated = response.truncated
        if response.snapshot_sha256 != compute_sha256(normalized_text):
            raise ScraperProviderError(
                "normalization_integrity",
                "adapter snapshot hash does not match normalized text",
            )
        if response.word_count != len(normalized_text.split()):
            raise ScraperProviderError(
                "normalization_integrity",
                "adapter word count does not match normalized text",
            )
    else:
        normalized_text, truncated = _truncate_text(response.text)
    if not normalized_text:
        record = _retrieval_record(
            run_id,
            retrieval_attempt_id,
            query,
            rank,
            original_url,
            response.resolved_url,
            RetrievalStatus.FAILED,
            retrieved_at,
        )
        return (
            RetrievalOutcome(
                retrieval=record,
                scrape_status=ScrapeStatus.FAILED,
                content_type=content_type,
                attempts_made=attempts_made,
                failure_code="empty_content",
                failure_message="scraper returned no textual content",
            ),
            None,
        )

    content_hash = compute_sha256(normalized_text)
    with deduplication.lock:
        snapshot_id = deduplication.resolved_urls.get(response.resolved_url)
        duplicate_status = ScrapeStatus.DUPLICATE_URL
        if snapshot_id is None:
            snapshot_id = deduplication.content_hashes.get(content_hash)
            duplicate_status = ScrapeStatus.DUPLICATE_CONTENT
        if snapshot_id is not None:
            deduplication.original_urls[original_url] = snapshot_id
            deduplication.resolved_urls[response.resolved_url] = snapshot_id
            deduplication.resolved_by_original[original_url] = response.resolved_url
            record = _retrieval_record(
                run_id,
                retrieval_attempt_id,
                query,
                rank,
                original_url,
                response.resolved_url,
                RetrievalStatus.SKIPPED,
                retrieved_at,
            )
            return (
                RetrievalOutcome(
                    retrieval=record,
                    scrape_status=duplicate_status,
                    content_type=content_type,
                    attempts_made=attempts_made,
                    duplicate_of_snapshot_id=snapshot_id,
                ),
                None,
            )

        snapshot_id = uuid5(
            NAMESPACE_URL,
            f"phase-7b-snapshot::{run_id}::{response.resolved_url}::{content_hash}",
        )
        snapshot = build_source_snapshot(
            run_id=run_id,
            retrieval_attempt_id=retrieval_attempt_id,
            snapshot_id=snapshot_id,
            source_url=response.resolved_url,
            original_url=response.original_url or original_url,
            canonical_url=response.canonical_url,
            retrieved_at=retrieved_at,
            normalized_text=normalized_text,
            truncated=truncated,
            normalization_version=response.normalization_version,
            acquisition_version=response.acquisition_version,
            provider_name=response.provider_name,
            provider_version=response.provider_version,
            media_type_provenance=response.media_type_provenance,
            created_at=clock(),
        )
        family = identify_source_family(snapshot)
        family_snapshot_id = deduplication.source_families.get(family.source_family_id)
        if family_snapshot_id is not None:
            deduplication.original_urls[original_url] = family_snapshot_id
            deduplication.resolved_urls[response.resolved_url] = family_snapshot_id
            deduplication.resolved_by_original[original_url] = response.resolved_url
            record = _retrieval_record(
                run_id,
                retrieval_attempt_id,
                query,
                rank,
                original_url,
                response.resolved_url,
                RetrievalStatus.SKIPPED,
                retrieved_at,
            )
            return (
                RetrievalOutcome(
                    retrieval=record,
                    scrape_status=ScrapeStatus.DUPLICATE_CONTENT,
                    content_type=content_type,
                    attempts_made=attempts_made,
                    duplicate_of_snapshot_id=family_snapshot_id,
                ),
                None,
            )
        deduplication.original_urls[original_url] = snapshot_id
        deduplication.resolved_urls[response.resolved_url] = snapshot_id
        deduplication.content_hashes[content_hash] = snapshot_id
        deduplication.source_families[family.source_family_id] = snapshot_id
        deduplication.resolved_by_original[original_url] = response.resolved_url
        record = _retrieval_record(
            run_id,
            retrieval_attempt_id,
            query,
            rank,
            original_url,
            response.resolved_url,
            RetrievalStatus.RETRIEVED,
            retrieved_at,
        )
        return (
            RetrievalOutcome(
                retrieval=record,
                scrape_status=ScrapeStatus.RETRIEVED,
                content_type=content_type,
                provider_name=response.provider_name,
                provider_version=response.provider_version,
                canonical_url=response.canonical_url,
                normalization_version=response.normalization_version,
                acquisition_version=response.acquisition_version,
                media_type_provenance=response.media_type_provenance,
                snapshot_id=snapshot_id,
                attempts_made=attempts_made,
            ),
            snapshot,
        )


def _scrape_with_retry(
    scraper_provider: ScraperProvider,
    url: str,
    retry_policy: RetryPolicy,
    boundary_check: Callable[[], None] | None,
) -> tuple[ScrapeResponse | None, ScrapeStatus, str | None, str | None, int]:
    for attempt in range(1, retry_policy.max_attempts + 1):
        if boundary_check is not None:
            boundary_check()
        try:
            response = scraper_provider.scrape(
                ScrapeRequest(url=url, timeout_seconds=retry_policy.timeout_seconds)
            )
            if not isinstance(response, ScrapeResponse):
                raise ScraperProviderError("scraper provider returned a non-ScrapeResponse value")
            if boundary_check is not None:
                boundary_check()
            return response, ScrapeStatus.RETRIEVED, None, None, attempt
        except CooperativeCancellation:
            raise
        except (ScraperTimeoutError, TimeoutError) as exc:
            if attempt == retry_policy.max_attempts:
                return (
                    None,
                    ScrapeStatus.TIMEOUT,
                    "timeout",
                    str(exc) or "scrape timed out",
                    attempt,
                )
        except ScraperProviderError as exc:
            if exc.code in {"unsupported_content", "invalid_content_type"}:
                return None, ScrapeStatus.UNSUPPORTED, exc.code, None, attempt
            return None, ScrapeStatus.FAILED, exc.code, str(exc) or "scrape failed", attempt
        except Exception as exc:
            return (
                None,
                ScrapeStatus.FAILED,
                "unexpected_failure",
                f"unexpected scraper failure: {exc}",
                attempt,
            )
    raise RuntimeError("retry loop ended without a result")


def _queries_for_stance(planner: PlannerOutput, stance: Stance) -> list[SearchQuery]:
    queries = sorted(
        (query for query in planner.search_queries if query.stance is stance),
        key=lambda query: (query.provider.value, query.query_round),
    )
    expected = 4 if any(query.provider.value == "openalex" for query in queries) else 3
    if len(queries) != expected:
        raise ValueError(f"planner must provide exactly {expected} {stance.value} provider queries")
    return queries


def _query_with_exclusions(query: SearchQuery) -> str:
    if query.provider.value == "openalex":
        return query.query_text
    missing = missing_required_query_exclusions(query.exclusion_parameters)
    if missing:
        raise ValueError(f"query is missing required exclusions: {', '.join(missing)}")
    return f"{query.query_text} {query.exclusion_parameters}".strip()


def _retrieval_record(
    run_id: UUID,
    retrieval_attempt_id: UUID,
    query: SearchQuery,
    rank: int,
    original_url: str,
    resolved_url: str,
    status: RetrievalStatus,
    retrieved_at: datetime,
) -> RetrievalRecord:
    return RetrievalRecord(
        run_id=run_id,
        retrieval_attempt_id=retrieval_attempt_id,
        query_id=query.query_id,
        query_round=query.query_round,
        query_text=query.query_text,
        search_rank=rank,
        source_url=original_url,
        resolved_url=resolved_url,
        status=status,
        retrieved_at=retrieved_at,
    )


def _truncate_text(text: str) -> tuple[str, bool]:
    normalized = " ".join(text.split())
    matches = list(_WORD_RE.finditer(normalized))
    if len(matches) <= SNAPSHOT_WORD_LIMIT:
        return normalized, False
    return normalized[: matches[SNAPSHOT_WORD_LIMIT - 1].end()], True


def _normalized_content_type(content_type: str) -> str:
    return content_type.split(";", maxsplit=1)[0].strip().lower()


def _is_supported_content_type(content_type: str) -> bool:
    return content_type.startswith("text/") or content_type in {
        "application/pdf",
        "application/xhtml+xml",
        "application/xml",
    }


def _utc_now() -> datetime:
    return datetime.now(UTC)
