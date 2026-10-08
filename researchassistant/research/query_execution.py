"""One query execution owner for initial and authorized adaptive discovery."""

from __future__ import annotations

import hashlib
import json
import math
import time
from collections.abc import Callable, Mapping
from datetime import datetime
from decimal import ROUND_CEILING, Decimal
from pathlib import Path
from typing import Literal, TypeVar
from uuid import UUID

import httpx
from pydantic import ValidationError

from providers.discovery_transport import RequestKind, observe_physical_requests
from providers.search import (
    SearchFailureCode,
    SearchProvider,
    SearchProviderError,
    SearchRequest,
    SearchResponse,
    metadata_page_size,
    page_parameters,
)
from researchassistant.common.money import add_usd, parse_exact_usd
from researchassistant.contracts.discovery_v2 import (
    SearchMode,
    V2CompiledQueryAction,
    V2DiscoveryBinding,
    V2DiscoveryFailure,
    V2DiscoveryOperation,
    V2DiscoveryProviderBudget,
    V2MetadataDiscoveryPolicy,
    V2ProviderAttemptCompletion,
    V2ProviderAttemptStart,
    V2SanitizedParameter,
    discovery_hash,
    discovery_id,
)
from researchassistant.contracts.model_contracts import DiscoveryProvider, SearchIntent
from researchassistant.contracts.model_research import (
    V2AdaptiveSearchQuery,
    V2ProviderSearchBudget,
    V2RoundOneSearchQuery,
)
from researchassistant.contracts.research_directions import ResearchDirections
from researchassistant.research.discovery_capabilities import get_query_capabilities
from researchassistant.research.discovery_policy import build_discovery_binding
from researchassistant.research.query_compiler import QUERY_COMPILER_ID, validate_compiled_action
from researchassistant.storage.discovery_store import (
    bind_discovery_run,
    complete_provider_attempt,
    insert_discovery_operation,
    provider_attempt_audit,
    read_discovery_binding,
    reserve_provider_attempt,
)

_PROVIDER_CAPS = {
    DiscoveryProvider.OPENALEX: 10,
    DiscoveryProvider.ARXIV: 6,
    DiscoveryProvider.PUBMED: 6,
    DiscoveryProvider.EXA: 18,
    DiscoveryProvider.SERPSEARCH: 12,
}
# Distinct mode price bases are frozen even when current documented rates coincide.
_COSTS = {
    DiscoveryProvider.OPENALEX: Decimal("0.001"),
    DiscoveryProvider.EXA: Decimal("0.01"),
    DiscoveryProvider.SERPSEARCH: Decimal("0.01"),
    DiscoveryProvider.ARXIV: Decimal("0"),
    DiscoveryProvider.PUBMED: Decimal("0"),
}

_Query = TypeVar("_Query", V2RoundOneSearchQuery, V2AdaptiveSearchQuery)


def fair_query_order(queries: tuple[_Query, ...]) -> tuple[_Query, ...]:
    """Give fresh enabled lanes a first pass before a lane's additional strategies."""
    if any(
        query.compiled_query is None or query.compiled_query.compiler_identity != QUERY_COMPILER_ID
        for query in queries
    ):
        return queries
    counts: dict[tuple[object, DiscoveryProvider], int] = {}
    ordered = []
    for index, query in enumerate(queries):
        lane = (query.direction, query.provider)
        occurrence = counts.get(lane, 0)
        counts[lane] = occurrence + 1
        ordered.append((occurrence, index, query))
    return tuple(query for _occurrence, _index, query in sorted(ordered, key=lambda item: item[:2]))


def _request_cost(provider: DiscoveryProvider, depth: int) -> Decimal:
    """Freeze an upper bound for metadata-only auto searches, without widening totals."""
    if provider is DiscoveryProvider.EXA:
        count = min(depth, get_query_capabilities(provider).max_metadata_per_operation)
        documented = Decimal("0.007") + Decimal("0.001") * max(0, count - 10)
        return max(Decimal("0.01"), documented.quantize(Decimal("0.01"), rounding=ROUND_CEILING))
    return _COSTS[provider]


def _cost_identity(provider: DiscoveryProvider, mode: SearchMode, depth: int) -> str:
    if provider is DiscoveryProvider.EXA:
        return f"query-exa-{mode}-2026-10-07-v3-depth-{depth}"
    return f"query-{provider.value}-{mode}-2026-10-06-v2"


def freeze_query_execution(
    path: str,
    run_id: UUID,
    exact_claim: str,
    directions: ResearchDirections,
    providers: tuple[DiscoveryProvider, ...],
    clock: Callable[[], datetime],
    *,
    query_modes: Mapping[DiscoveryProvider, SearchMode] | None = None,
    provider_configuration_fingerprint: str = "injected-provider-policy-v1",
    provider_budgets: tuple[V2DiscoveryProviderBudget, ...] | None = None,
    discovery_policy: V2MetadataDiscoveryPolicy | None = None,
) -> V2DiscoveryBinding:
    if DiscoveryProvider.SERPER in providers:
        raise ValueError("Serper has no provider-native conceptual query compiler")
    policy = discovery_policy or V2MetadataDiscoveryPolicy()
    modes = dict(query_modes or {})
    if not set(modes) <= set(providers):
        raise ValueError("query mode settings cannot enable an unselected provider")
    frozen_modes = {}
    budgets = []
    for provider in providers:
        mode = modes.get(
            provider, "provider_default" if provider is DiscoveryProvider.EXA else "lexical"
        )
        get_query_capabilities(provider).require_search(mode, executable=True)
        frozen_modes[provider.value] = mode
        cost = _request_cost(provider, policy.metadata_depth)
        budgets.append(
            V2DiscoveryProviderBudget(
                provider=provider,
                max_requests=_PROVIDER_CAPS[provider],
                max_cost_usd=Decimal("0.01")
                if provider is DiscoveryProvider.OPENALEX
                else _COSTS[provider] * _PROVIDER_CAPS[provider],
                cost_policy_identity=_cost_identity(provider, mode, policy.metadata_depth),
                reservation_per_request_usd=cost,
                cost_basis="documented_free" if cost == 0 else "configured_upper_bound",
            )
        )
    if provider_budgets is None:
        try:
            existing = read_discovery_binding(path, run_id)
            provider_budgets = existing.provider_budgets
        except KeyError:
            pass
    if provider_budgets is not None:
        if tuple(item.provider for item in provider_budgets) != providers:
            raise ValueError("configured request budgets must match the enabled providers")
        for configured, default in zip(provider_budgets, budgets, strict=True):
            if (
                configured.max_requests > default.max_requests
                or configured.max_cost_usd > default.max_cost_usd
                or configured.reservation_per_request_usd != default.reservation_per_request_usd
                or configured.cost_basis != default.cost_basis
                or configured.cost_policy_identity != default.cost_policy_identity
            ):
                raise ValueError("configured request budgets cannot widen the compiled policy")
        budgets = list(provider_budgets)
    config_hash = discovery_hash(
        json.dumps(
            {"modes": frozen_modes, "provider": provider_configuration_fingerprint}, sort_keys=True
        )
    )
    root = Path(__file__).resolve().parents[2]
    binding = build_discovery_binding(
        run_id=run_id,
        exact_claim=exact_claim,
        directions=directions,
        providers=providers,
        policy=policy,
        capabilities=tuple(get_query_capabilities(x) for x in providers),
        provider_budgets=tuple(budgets),
        provider_configuration_hash=config_hash,
        source_root=root,
    )
    # Freeze new executable prompt/schema identity without relabeling Phase-1 history.
    prompt_hashes = {
        name: hashlib.sha256((root / "prompts" / name).read_bytes()).hexdigest()
        for name in ("v2_initial_planner_v2.md", "search_agent_v2.md", "v2_scout_v2.md")
    }
    from researchassistant.contracts.acquisition_ranking import (
        V2AcquisitionRankingAudit,
        V2DiscoveryPipelineCounters,
    )
    from researchassistant.contracts.metadata_ranking import V2MetadataRankingArtifact
    from researchassistant.contracts.query_planning import (
        V2AdaptiveSearchConceptsOutput,
        V2InitialPlannerConceptsOutput,
    )
    from researchassistant.contracts.query_retrieval import (
        V2QueryPageCheckpoint,
        V2QueryParseReceipt,
        V2QueryRetrievalResult,
    )

    schema_hash = discovery_hash(
        json.dumps(
            {
                "foundation": binding.prompt_schema_hash,
                "prompts": prompt_hashes,
                "schemas": [
                    V2InitialPlannerConceptsOutput.model_json_schema(),
                    V2AdaptiveSearchConceptsOutput.model_json_schema(),
                    V2MetadataRankingArtifact.model_json_schema(),
                    V2AcquisitionRankingAudit.model_json_schema(),
                    V2DiscoveryPipelineCounters.model_json_schema(),
                    V2QueryPageCheckpoint.model_json_schema(),
                    V2QueryParseReceipt.model_json_schema(),
                    V2QueryRetrievalResult.model_json_schema(),
                ],
            },
            sort_keys=True,
        )
    )
    binding = binding.model_copy(
        update={
            "compiler_identity": QUERY_COMPILER_ID,
            "ranking_identity": "source-candidate-ranking-v2",
            "prompt_schema_hash": schema_hash,
        }
    )
    bind_discovery_run(path, binding, clock())
    return binding


def query_provider_budgets(
    providers: tuple[DiscoveryProvider, ...],
    adapters: Mapping[DiscoveryProvider, SearchProvider],
    query_modes: Mapping[DiscoveryProvider, SearchMode] | None,
    *,
    discovery_policy: V2MetadataDiscoveryPolicy | None = None,
) -> tuple[V2DiscoveryProviderBudget, ...]:
    policy = discovery_policy or V2MetadataDiscoveryPolicy()
    results = []
    for provider in providers:
        if provider not in _PROVIDER_CAPS:
            raise ValueError(f"unsupported compiled discovery provider: {provider.value}")
        mode = (query_modes or {}).get(
            provider, "provider_default" if provider is DiscoveryProvider.EXA else "lexical"
        )
        cost = _request_cost(provider, policy.metadata_depth)
        method = getattr(adapters[provider], "query_budget", None)
        configured = method(provider, mode) if callable(method) else None
        results.append(
            configured
            or V2DiscoveryProviderBudget(
                provider=provider,
                max_requests=_PROVIDER_CAPS[provider],
                max_cost_usd=_COSTS[provider] * _PROVIDER_CAPS[provider],
                reservation_per_request_usd=cost,
                cost_basis="documented_free" if cost == 0 else "configured_upper_bound",
                cost_policy_identity=_cost_identity(provider, mode, policy.metadata_depth),
            )
        )
    return tuple(results)


def available_query_budgets(path: str, run_id: UUID) -> tuple[V2ProviderSearchBudget, ...]:
    """Expose actual physical request headroom, including retries and PubMed summaries."""
    binding = read_discovery_binding(path, run_id)
    audit = provider_attempt_audit(path, run_id)
    if audit.interrupted_unknown:
        return ()
    results = []
    for budget in binding.provider_budgets:
        pairs = tuple(
            (start, completion)
            for start, completion in zip(audit.starts, audit.completions, strict=True)
            if start.provider == budget.provider
        )
        spent = add_usd(
            *(
                max(
                    start.reserved_cost_usd,
                    completion.actual_cost_usd
                    if completion and completion.actual_cost_usd is not None
                    else start.reserved_cost_usd,
                )
                for start, completion in pairs
            )
        )
        remaining = max(0, budget.max_requests - len(pairs))
        if budget.reservation_per_request_usd:
            affordable = 0
            exposure = spent
            for _ in range(remaining):
                exposure = add_usd(exposure, budget.reservation_per_request_usd)
                if exposure > budget.max_cost_usd:
                    break
                affordable += 1
            remaining = affordable
        capability = next(x for x in binding.capabilities if x.provider == budget.provider)
        if remaining >= capability.physical_requests_per_page:
            results.append(
                V2ProviderSearchBudget(
                    provider=budget.provider,
                    attempted_calls=len(pairs),
                    maximum_calls=len(pairs) + remaining,
                )
            )
    return tuple(results)


def _failure(code: str, *, unknown: bool = False, retryable: bool = False) -> V2DiscoveryFailure:
    mapping = {
        "timeout": "timeout",
        "connection_failure": "connection",
        "transient_outage": "connection",
        "rate_limit": "rate_limit",
        "authentication_failure": "authentication",
        "budget_exhausted": "budget",
        "cancelled": "cancelled",
    }
    return V2DiscoveryFailure(
        code="interrupted" if unknown else mapping.get(code, "invalid_request"),
        retryable=retryable and not unknown,
        detail="unknown_after_start" if unknown else "provider_failure",
    )


class _PhysicalExecution:
    def __init__(
        self,
        path: str,
        action: V2CompiledQueryAction,
        binding: V2DiscoveryBinding,
        clock: Callable[[], datetime],
        cancelled: Callable[[], bool] | None,
    ) -> None:
        self.path = path
        self.action = action
        self.binding = binding
        self.clock = clock
        self.cancelled = cancelled
        self.sequence = 0
        self.parent: V2ProviderAttemptCompletion | None = None
        self.pubmed_ids: tuple[str, ...] = ()
        self.completions: list[V2ProviderAttemptCompletion] = []
        self.starts: list[V2ProviderAttemptStart] = []

    def request(
        self,
        request: SearchRequest,
        parameters: Mapping[str, str | int | bool],
        send: Callable[[], httpx.Response],
        *,
        request_kind: RequestKind,
        before_reservation: Callable[[Callable[[], bool] | None], None] | None = None,
    ) -> httpx.Response:
        if request.compiled_query != self.action or request.run_id != self.action.run_id:
            raise SearchProviderError(
                SearchFailureCode.PERMANENT_FAILURE, "physical request differs from its owner"
            )
        expected = page_parameters(request)
        if request_kind == "metadata":
            if (
                request.provider is not DiscoveryProvider.PUBMED
                or not self.parent
                or not self.pubmed_ids
            ):
                raise SearchProviderError(
                    SearchFailureCode.PERMANENT_FAILURE, "metadata request lacks owned identifiers"
                )
            expected = {"db": "pubmed", "id": ",".join(self.pubmed_ids), "retmode": "json"}
        if set(parameters) != set(expected) or any(
            type(parameters[name]) is not type(value) or parameters[name] != value
            for name, value in expected.items()
        ):
            raise SearchProviderError(
                SearchFailureCode.PERMANENT_FAILURE,
                "physical parameters differ from compiled policy",
            )
        budget = next(x for x in self.binding.provider_budgets if x.provider == request.provider)
        while True:
            if before_reservation is not None:
                before_reservation(self.cancelled)
            if self.cancelled and self.cancelled():
                raise SearchProviderError(
                    SearchFailureCode.CANCELLED,
                    "query cancelled before physical request reservation",
                )
            self.sequence += 1
            key = f"attempt/{self.action.fingerprint}/{self.sequence}"
            start = V2ProviderAttemptStart(
                run_id=request.run_id,
                artifact_id=discovery_id(self.action.run_id, "V2ProviderAttemptStart", key),
                identity_key=key,
                operation_id=self.action.artifact_id,
                binding_fingerprint=self.binding.fingerprint,
                provider=request.provider,
                sequence=self.sequence,
                page_number=request.page_number,
                request_kind=request_kind,
                parent_attempt_id=self.parent.attempt_id
                if request_kind == "metadata" and self.parent
                else None,
                parent_response_hash=self.parent.response_hash
                if request_kind == "metadata" and self.parent
                else None,
                parameters=tuple(
                    V2SanitizedParameter(name=k, value=v) for k, v in parameters.items()
                ),
                requested_records=request.limit,
                reserved_cost_usd=budget.reservation_per_request_usd,
                cost_basis=budget.cost_basis,
                started_at=self.clock(),
            )
            try:
                reserve_provider_attempt(self.path, start)
                self.starts.append(start)
            except ValueError as exc:
                raise SearchProviderError(SearchFailureCode.BUDGET_EXHAUSTED, str(exc)) from exc
            try:
                response = send()
            except BaseException:
                self._complete(
                    start,
                    status="interrupted_unknown",
                    failure=_failure("interrupted", unknown=True),
                )
                raise
            if request_kind == "primary":
                self.pubmed_ids = ()
            success = 200 <= response.status_code < 300
            actual: Decimal | None = (
                Decimal("0") if budget.cost_basis == "documented_free" else None
            )
            if request.provider in {DiscoveryProvider.OPENALEX, DiscoveryProvider.EXA}:
                try:
                    body = response.json()
                    raw_cost = (
                        body.get("meta", {}).get("cost_usd")
                        if request.provider is DiscoveryProvider.OPENALEX
                        else body.get("costDollars", {}).get("total")
                    )
                    if raw_cost is not None:
                        actual = parse_exact_usd(raw_cost)
                except (ValueError, TypeError, AttributeError):
                    pass
            completion = self._complete(
                start,
                status="completed" if success else "failed",
                response_hash=hashlib.sha256(response.content).hexdigest() if success else None,
                failure=None
                if success
                else _failure(
                    "authentication_failure"
                    if response.status_code in {401, 403}
                    else "rate_limit"
                    if response.status_code == 429
                    else "timeout"
                    if response.status_code in {408, 504}
                    else "transient_outage"
                    if response.status_code >= 500
                    else "provider_failure",
                    retryable=actual is not None and response.status_code in {429, 502, 503, 504},
                ),
                actual=actual,
                metadata_records=self._metadata_records(response, request) if success else 0,
            )
            if success:
                if request_kind == "primary":
                    self.parent = completion
                return response
            # Retry only a response known to have failed, never an unknown outcome.
            # Paid responses lacking reported cost retain exposure and stop further work.
            if (
                response.status_code not in {429, 502, 503, 504}
                or self.sequence
                >= self.action.policy.max_pages_per_operation
                - (
                    1
                    if request.provider is DiscoveryProvider.PUBMED and request_kind == "primary"
                    else 0
                )
                or actual is None
            ):
                return response
            # Respect documented throttling before another separately charged attempt.
            # A longer or unparseable delay terminates this bounded operation.
            try:
                delay = float(response.headers.get("retry-after", "1"))
            except ValueError:
                return response
            if not math.isfinite(delay) or not 0 <= delay <= 5:
                return response
            deadline = time.monotonic() + delay
            while time.monotonic() < deadline:
                if self.cancelled and self.cancelled():
                    raise SearchProviderError(
                        SearchFailureCode.CANCELLED, "query cancelled during retry delay"
                    )
                time.sleep(min(0.05, max(0, deadline - time.monotonic())))

    def _metadata_records(self, response: httpx.Response, request: SearchRequest) -> int:
        """Count bounded returned metadata without admitting it as evidence."""
        try:
            body = response.json()
            if request.provider is DiscoveryProvider.PUBMED:
                ids = body.get("esearchresult", {}).get("idlist")
                if isinstance(ids, list):
                    if len(ids) <= request.limit and all(
                        isinstance(item, str)
                        and item.isascii()
                        and item.isdecimal()
                        and len(item) <= 20
                        for item in ids
                    ):
                        self.pubmed_ids = tuple(ids)
                    return min(len(ids), request.limit)
                records = body.get("result", {})
                return sum(item in records for item in self.pubmed_ids)
            records = (
                body.get("organic_results", [])
                if request.provider is DiscoveryProvider.SERPSEARCH
                else body.get("results", [])
            )
            record_cap = (
                request.compiled_query.capabilities.max_metadata_per_page
                if request.provider is DiscoveryProvider.SERPSEARCH and request.compiled_query
                else request.limit
            )
            return min(len(records), record_cap) if isinstance(records, list) else 0
        except (ValueError, TypeError, AttributeError):
            if request.provider is DiscoveryProvider.ARXIV:
                from xml.etree import ElementTree

                try:
                    return min(
                        len(
                            ElementTree.fromstring(response.content).findall(
                                "{http://www.w3.org/2005/Atom}entry"
                            )
                        ),
                        request.limit,
                    )
                except ElementTree.ParseError:
                    pass
            return 0

    def _complete(
        self,
        start: V2ProviderAttemptStart,
        *,
        status: Literal["completed", "failed", "interrupted_unknown"],
        failure: V2DiscoveryFailure | None = None,
        response_hash: str | None = None,
        actual: Decimal | None = None,
        metadata_records: int = 0,
    ) -> V2ProviderAttemptCompletion:
        key = f"completion/{start.artifact_id}"
        completion = V2ProviderAttemptCompletion(
            run_id=start.run_id,
            artifact_id=discovery_id(start.run_id, "V2ProviderAttemptCompletion", key),
            identity_key=key,
            attempt_id=start.artifact_id,
            operation_id=start.operation_id,
            status=status,
            response_hash=response_hash,
            failure=failure,
            actual_cost_usd=actual,
            metadata_records=metadata_records,
            cost_basis="unknown"
            if actual is None
            else "documented_free"
            if actual == 0 and start.cost_basis == "documented_free"
            else "reported",
            completed_at=self.clock(),
        )
        complete_provider_attempt(self.path, completion, completion.completed_at)
        self.completions.append(completion)
        return completion


def execute_query(
    *,
    path: str,
    run_id: UUID,
    provider: DiscoveryProvider,
    query_text: str,
    compiled_query: V2CompiledQueryAction | None,
    providers: Mapping[DiscoveryProvider, SearchProvider],
    clock: Callable[[], datetime],
    cancellation_requested: Callable[[], bool] | None = None,
) -> SearchResponse:
    adapter = providers.get(provider)
    if adapter is None:
        raise SearchProviderError(
            SearchFailureCode.MISSING_CONFIGURATION, f"{provider.value} is not configured"
        )
    intent = (
        SearchIntent.ACADEMIC_STUDY
        if provider
        in {DiscoveryProvider.OPENALEX, DiscoveryProvider.ARXIV, DiscoveryProvider.PUBMED}
        else SearchIntent.BROAD_WEB
    )
    if compiled_query is None:
        try:
            binding = read_discovery_binding(path, run_id)
        except KeyError:
            binding = None
        if binding is not None and binding.compiler_identity == QUERY_COMPILER_ID:
            raise SearchProviderError(
                SearchFailureCode.PERMANENT_FAILURE,
                "fresh compiled-query runs require an application-owned compiled action",
            )
        return adapter.search(
            SearchRequest(
                run_id=run_id, provider=provider, intent=intent, query_text=query_text, limit=5
            )
        )
    validate_compiled_action(compiled_query)
    if (
        compiled_query.run_id != run_id
        or compiled_query.conceptual_query.provider != provider
        or compiled_query.query_text != query_text
    ):
        raise SearchProviderError(
            SearchFailureCode.PERMANENT_FAILURE, "compiled query does not match execution owner"
        )
    binding = read_discovery_binding(path, run_id)
    budget = next(x for x in binding.provider_budgets if x.provider == provider)
    if f"-{compiled_query.mode}-" not in budget.cost_policy_identity:
        raise SearchProviderError(
            SearchFailureCode.PERMANENT_FAILURE,
            "query mode differs from frozen request cost policy",
        )
    return _execute_metadata_operation(
        path=path,
        run_id=run_id,
        provider=provider,
        adapter=adapter,
        intent=intent,
        action=compiled_query,
        binding=binding,
        clock=clock,
        cancellation_requested=cancellation_requested,
    )


def _bounded_response(response: SearchResponse, limit: int) -> SearchResponse:
    """Bound retained provider metadata before persistence and any model rendering."""
    results = []
    for result in response.results[:limit]:
        metadata = result.metadata.model_dump()
        for name, value in metadata.items():
            if isinstance(value, str):
                metadata[name] = value[: 8000 if name == "abstract" else 2000]
        results.append(
            result.model_copy(
                update={
                    "title": result.title[:1000],
                    "snippet": result.snippet[:4000] if result.snippet else None,
                    "metadata": result.metadata.model_validate(metadata),
                }
            )
        )
    return response.model_copy(
        update={
            "results": results,
            "warnings": tuple(value[:256] for value in response.warnings[:8]),
        }
    )


def _search_metadata_page(
    adapter: SearchProvider, request: SearchRequest, observer: _PhysicalExecution
) -> SearchResponse:
    with observe_physical_requests(observer):
        before = observer.sequence
        if getattr(adapter, "physical_accounting", False):
            response = adapter.search(request)
            if observer.sequence == before:
                raise SearchProviderError(
                    SearchFailureCode.PERMANENT_FAILURE,
                    "adapter omitted required physical request accounting",
                )
            return response
        if request.provider is DiscoveryProvider.PUBMED:
            raise SearchProviderError(
                SearchFailureCode.PERMANENT_FAILURE,
                "PubMed adapter must expose both physical metadata requests",
            )
        result: SearchResponse | None = None

        def send() -> httpx.Response:
            nonlocal result
            result = adapter.search(request)
            body: dict[str, object] = {
                "organic_results"
                if request.provider is DiscoveryProvider.SERPSEARCH
                else "results": [x.model_dump(mode="json") for x in result.results]
            }
            if result.cost_usd is not None:
                if request.provider is DiscoveryProvider.EXA:
                    body["costDollars"] = {"total": str(result.cost_usd)}
                else:
                    body["meta"] = {"cost_usd": str(result.cost_usd)}
            return httpx.Response(200, json=body)

        observer.request(request, page_parameters(request), send, request_kind="primary")
        if result is None:
            raise RuntimeError("query execution omitted its response")
        return result


def _execute_metadata_operation(
    *,
    path: str,
    run_id: UUID,
    provider: DiscoveryProvider,
    adapter: SearchProvider,
    intent: SearchIntent,
    action: V2CompiledQueryAction,
    binding: V2DiscoveryBinding,
    clock: Callable[[], datetime],
    cancellation_requested: Callable[[], bool] | None,
) -> SearchResponse:
    from providers.ranking import canonical_discovery_url
    from researchassistant.contracts.query_retrieval import (
        V2QueryPageCheckpoint,
        V2QueryParseReceipt,
        V2QueryRetrievalResult,
    )
    from researchassistant.storage.discovery_store import read_discovery_operation
    from researchassistant.storage.query_retrieval_store import (
        parse_receipt_key,
        persist_page,
        read_pages,
        retention_headroom,
    )
    from researchassistant.storage.store import insert_v2_artifact, read_v2_artifact

    result_key = f"metadata-retrieval-v2:{action.artifact_id}:result"
    try:
        envelope = read_v2_artifact(path, run_id, result_key)
        if envelope.artifact_type != "V2QueryRetrievalResult":
            raise ValueError("cached metadata result has conflicting artifact type")
        cached = V2QueryRetrievalResult.model_validate_json(envelope.payload_json)
    except KeyError:
        cached = None
    if cached is not None:
        if (
            cached.run_id != run_id
            or cached.operation_id != action.artifact_id
            or cached.binding_fingerprint != binding.fingerprint
        ):
            raise ValueError("cached metadata retrieval result has conflicting ownership")
        # Revalidate the underlying physical provenance even for fully cached results.
        owned_pages = sorted(
            (page for page in read_pages(path, run_id) if page.operation_id == action.artifact_id),
            key=lambda page: page.page_number,
        )
        if [page.page_number for page in owned_pages] != list(range(1, len(owned_pages) + 1)):
            raise ValueError("cached metadata page checkpoints must be dense")
        expected_results = []
        expected_seen = set()
        for page in owned_pages:
            for result in page.response.results:
                identity = canonical_discovery_url(result.original_url)
                if identity not in expected_seen:
                    expected_seen.add(identity)
                    expected_results.append(result)
        owned_audit = provider_attempt_audit(path, run_id)
        expected_raw = sum(
            completion.metadata_records
            for start, completion in zip(owned_audit.starts, owned_audit.completions, strict=True)
            if start.operation_id == action.artifact_id
            and start.request_kind == "primary"
            and completion is not None
        )
        if (
            cached.response.results != expected_results
            or cached.page_count != len(owned_pages)
            or cached.retained_records != len(expected_results)
            or cached.raw_hits != expected_raw
            or cached.requested_depth != action.requested_depth
            or cached.effective_depth > action.effective_depth
        ):
            raise ValueError("cached metadata retrieval differs from owned parsed pages")
        if not cached.response.results and cached.stopping_reason in {
            "unknown_outcome",
            "provider_failure",
            "malformed_page",
            "completed_without_checkpoint",
            "provider_budget",
        }:
            raise SearchProviderError(
                SearchFailureCode.PERMANENT_FAILURE,
                "a started operation cannot be replayed; retained exposure requires a fresh run",
            )
        return cached.response
    key = f"operation/{action.fingerprint}"
    try:
        operation = read_discovery_operation(path, run_id, key)
    except KeyError:
        operation = V2DiscoveryOperation(
            run_id=run_id,
            artifact_id=discovery_id(run_id, "V2DiscoveryOperation", key),
            identity_key=key,
            binding_fingerprint=binding.fingerprint,
            action=action,
            created_at=clock(),
        )
        insert_discovery_operation(path, operation, operation.created_at)
    if operation.action != action or operation.binding_fingerprint != binding.fingerprint:
        raise ValueError("metadata operation differs from its immutable checkpoint")
    pages = sorted(
        (page for page in read_pages(path, run_id) if page.operation_id == action.artifact_id),
        key=lambda page: page.page_number,
    )
    if [page.page_number for page in pages] != list(range(1, len(pages) + 1)):
        raise ValueError("metadata page checkpoints must be dense")
    audit = provider_attempt_audit(path, run_id)
    starts = tuple(start for start in audit.starts if start.operation_id == action.artifact_id)
    checkpointed = {attempt_id for page in pages for attempt_id in page.attempt_ids}
    unparsed = [
        start
        for start in starts
        if start.artifact_id not in checkpointed
        and next(
            (
                completion
                for completion in audit.completions
                if completion
                and completion.attempt_id == start.artifact_id
                and completion.status == "completed"
            ),
            None,
        )
    ]
    observer = _PhysicalExecution(path, action, binding, clock, cancellation_requested)
    observer.sequence = len(starts)
    results = []
    seen: set[str] = set()
    for page in pages:
        for result in page.response.results:
            identity = canonical_discovery_url(result.original_url)
            if identity not in seen:
                seen.add(identity)
                results.append(result)
    raw_hits = sum(page.raw_hits for page in pages)
    completed_pages = len(pages)
    reason = "depth_reached"
    pending_error: SearchProviderError | None = None
    headroom = retention_headroom(path, run_id, action.conceptual_query.round_number)
    available = next(
        (
            budget.remaining_calls
            for budget in available_query_budgets(path, run_id)
            if budget.provider == provider
        ),
        0,
    )
    physical_per_page = action.capabilities.physical_requests_per_page
    page_size = metadata_page_size(action)
    remaining_pages = (
        min(action.policy.max_pages_per_operation - observer.sequence, available)
        // physical_per_page
    )
    if action.capabilities.executable_pagination == "none" or action.mode == "semantic":
        remaining_pages = min(remaining_pages, max(0, 1 - completed_pages))
    effective = min(
        action.effective_depth, raw_hits + page_size * remaining_pages, raw_hits + headroom
    )
    if audit.interrupted_unknown:
        reason = "unknown_outcome"
    elif unparsed:
        reason = "completed_without_checkpoint"
    elif effective == raw_hits and raw_hits < action.effective_depth:
        reason = "retention_cap" if headroom == 0 else "provider_budget"
    else:
        cursor = pages[-1].response.next_cursor if pages else None
        used_cursors = set()
        for page in pages[:-1]:
            if page.response.next_cursor:
                used_cursors.add(page.response.next_cursor)
        # A checkpointed terminal page remains terminal on replay after cancellation.
        if pages and not pages[-1].response.results:
            reason = "empty_page"
        elif len(pages) > 1 and {
            canonical_discovery_url(result.original_url) for result in pages[-1].response.results
        } <= {
            canonical_discovery_url(result.original_url)
            for page in pages[:-1]
            for result in page.response.results
        }:
            reason = "no_new_results"
        elif pages and pages[-1].raw_hits < pages[-1].requested_records:
            reason = "provider_limit"
        elif (
            pages
            and action.capabilities.executable_pagination == "cursor"
            and action.mode != "semantic"
            and cursor in used_cursors
        ):
            reason = "repeated_cursor"
        elif (
            pages
            and action.capabilities.executable_pagination == "cursor"
            and action.mode != "semantic"
            and not cursor
            and raw_hits < effective
        ):
            reason = "provider_limit"
        else:
            for page_number in range(completed_pages + 1, completed_pages + remaining_pages + 1):
                if raw_hits >= effective:
                    break
                if cancellation_requested and cancellation_requested():
                    raise SearchProviderError(
                        SearchFailureCode.CANCELLED, "query cancelled before next metadata page"
                    )
                limit = min(page_size, effective - raw_hits)
                try:
                    request = SearchRequest(
                        run_id=run_id,
                        provider=provider,
                        intent=intent,
                        semantic=action.mode == "semantic",
                        query_text=action.query_text,
                        limit=limit,
                        compiled_query=action,
                        page_number=page_number,
                        page_cursor=cursor,
                    )
                    before = len(observer.completions)
                    try:
                        response = _search_metadata_page(adapter, request, observer)
                    except SearchProviderError as empty_error:
                        if empty_error.code is not SearchFailureCode.EMPTY_RESULTS:
                            raise
                        response = SearchResponse(results=[], provider_name=provider.value)
                    response = _bounded_response(response, limit)
                    ranks = [result.rank for result in response.results]
                    offset = (page_number - 1) * page_size
                    if ranks != sorted(set(ranks)) or any(
                        rank <= offset or rank > offset + limit for rank in ranks
                    ):
                        raise SearchProviderError(
                            SearchFailureCode.MALFORMED_RESPONSE,
                            "metadata page has inconsistent provider ranks",
                        )
                    completed = tuple(
                        completion
                        for completion in observer.completions[before:]
                        if completion.status == "completed"
                    )
                    if not completed:
                        raise ValueError("metadata page lacks successful physical completion")
                    page = V2QueryPageCheckpoint(
                        run_id=run_id,
                        operation_id=action.artifact_id,
                        binding_fingerprint=binding.fingerprint,
                        page_number=page_number,
                        round_number=action.conceptual_query.round_number,
                        requested_records=limit,
                        raw_hits=sum(
                            item.metadata_records
                            for item in completed
                            if any(
                                start.artifact_id == item.attempt_id
                                and start.request_kind == "primary"
                                for start in observer.starts
                            )
                        ),
                        attempt_ids=tuple(item.attempt_id for item in completed),
                        response_hashes=tuple(item.response_hash for item in completed),
                        response=response,
                    )
                    # Persist the trusted parser's output independently of replayable pages.
                    # A forged page cannot reuse a genuine physical hash with new candidates.
                    receipt = V2QueryParseReceipt(
                        run_id=run_id,
                        operation_id=action.artifact_id,
                        binding_fingerprint=binding.fingerprint,
                        page_number=page_number,
                        attempt_ids=page.attempt_ids,
                        response_hashes=page.response_hashes,
                        parsed_response_hash=discovery_hash(response.model_dump_json()),
                    )
                    insert_v2_artifact(
                        path, parse_receipt_key(action.artifact_id, page_number), receipt, clock()
                    )
                    persist_page(path, page, clock())
                    pages.append(page)
                    completed_pages += 1
                except SearchProviderError as exc:
                    if exc.code is SearchFailureCode.CANCELLED:
                        raise
                    pending_error = exc
                    current = provider_attempt_audit(path, run_id)
                    reason = (
                        "unknown_outcome"
                        if current.interrupted_unknown
                        else "malformed_page"
                        if exc.code is SearchFailureCode.MALFORMED_RESPONSE
                        else "provider_budget"
                        if exc.code is SearchFailureCode.BUDGET_EXHAUSTED
                        else "provider_failure"
                    )
                    break
                except ValidationError:
                    pending_error = SearchProviderError(
                        SearchFailureCode.MALFORMED_RESPONSE,
                        "provider returned invalid bounded metadata",
                    )
                    reason = "malformed_page"
                    break
                except (httpx.HTTPError, TimeoutError, ConnectionError):
                    reason = "unknown_outcome"
                    break
                raw_hits += page.raw_hits
                new = 0
                for result in response.results:
                    identity = canonical_discovery_url(result.original_url)
                    if identity not in seen:
                        seen.add(identity)
                        results.append(result)
                        new += 1
                if not response.results:
                    reason = "empty_page"
                    break
                if not new:
                    reason = "no_new_results"
                    break
                if page.raw_hits < limit:
                    reason = "provider_limit"
                    break
                if (
                    action.capabilities.executable_pagination == "cursor"
                    and action.mode != "semantic"
                ):
                    cursor = response.next_cursor
                    if cursor is None:
                        reason = "provider_limit" if raw_hits < effective else "depth_reached"
                        break
                    if cursor in used_cursors:
                        reason = "repeated_cursor"
                        break
                    used_cursors.add(cursor)
                if observer.sequence >= action.policy.max_pages_per_operation:
                    break
    if reason == "depth_reached" and raw_hits < action.effective_depth:
        reason = (
            "retention_cap"
            if effective == raw_hits and headroom < action.effective_depth
            else "provider_budget"
        )
    if reason == "depth_reached" and action.effective_depth < action.requested_depth:
        reason = "provider_limit"
    response = SearchResponse(
        results=results,
        provider_name=pages[0].response.provider_name if pages else provider.value,
        provider_version=pages[0].response.provider_version if pages else "unknown",
        adapter_version="metadata-retrieval-v2",
        cost_usd=add_usd(*(page.response.cost_usd for page in pages))
        if pages and all(page.response.cost_usd is not None for page in pages)
        else None,
        warnings=() if reason == "depth_reached" else (f"metadata retrieval stopped: {reason}",),
        degraded_pool=reason
        in {
            "unknown_outcome",
            "malformed_page",
            "provider_failure",
            "completed_without_checkpoint",
        },
    )
    final_audit = provider_attempt_audit(path, run_id)
    recorded_raw = sum(
        completion.metadata_records
        for start, completion in zip(final_audit.starts, final_audit.completions, strict=True)
        if start.operation_id == action.artifact_id
        and start.request_kind == "primary"
        and completion is not None
    )
    result = V2QueryRetrievalResult(
        run_id=run_id,
        operation_id=action.artifact_id,
        binding_fingerprint=binding.fingerprint,
        requested_depth=action.requested_depth,
        effective_depth=effective,
        raw_hits=recorded_raw,
        retained_records=len(results),
        page_count=completed_pages,
        stopping_reason=reason,
        response=response,
    )
    insert_v2_artifact(path, result_key, result, clock())
    if not results and pending_error is not None:
        raise pending_error
    if not results and reason == "unknown_outcome":
        raise SearchProviderError(
            SearchFailureCode.PERMANENT_FAILURE,
            "unknown request outcome stops further provider attempts; require a fresh run",
        )
    if not results and reason == "completed_without_checkpoint":
        raise SearchProviderError(
            SearchFailureCode.PERMANENT_FAILURE,
            "completed physical response cannot be replayed without a parsed checkpoint",
        )
    if not results and reason == "provider_budget":
        raise SearchProviderError(
            SearchFailureCode.BUDGET_EXHAUSTED, "provider request budget is exhausted"
        )
    return response
