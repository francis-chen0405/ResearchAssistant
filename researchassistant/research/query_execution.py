"""One query execution owner for initial and authorized adaptive discovery."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Literal
from uuid import UUID

import httpx

from providers.discovery_transport import RequestKind, observe_physical_requests
from providers.search import (
    SearchFailureCode,
    SearchProvider,
    SearchProviderError,
    SearchRequest,
    SearchResponse,
)
from researchassistant.common.money import add_usd, parse_exact_usd
from researchassistant.contracts.discovery_v2 import (
    SearchMode,
    V2CompiledQueryAction,
    V2DiscoveryBinding,
    V2DiscoveryFailure,
    V2DiscoveryOperation,
    V2DiscoveryPolicy,
    V2DiscoveryProviderBudget,
    V2ProviderAttemptCompletion,
    V2ProviderAttemptStart,
    V2SanitizedParameter,
    discovery_hash,
    discovery_id,
)
from researchassistant.contracts.model_contracts import DiscoveryProvider, SearchIntent
from researchassistant.contracts.model_research import V2ProviderSearchBudget
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
) -> V2DiscoveryBinding:
    if DiscoveryProvider.SERPER in providers:
        raise ValueError("Serper has no provider-native conceptual query compiler")
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
        cost = _COSTS[provider]
        budgets.append(
            V2DiscoveryProviderBudget(
                provider=provider,
                max_requests=_PROVIDER_CAPS[provider],
                max_cost_usd=Decimal("0.01")
                if provider is DiscoveryProvider.OPENALEX
                else cost * _PROVIDER_CAPS[provider],
                cost_policy_identity=f"query-{provider.value}-{mode}-2026-10-06-v2",
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
        policy=V2DiscoveryPolicy(),
        capabilities=tuple(get_query_capabilities(x) for x in providers),
        provider_budgets=tuple(budgets),
        provider_configuration_hash=config_hash,
        source_root=root,
    )
    # Freeze new executable prompt/schema identity without relabeling Phase-1 history.
    prompt_hashes = {
        name: hashlib.sha256((root / "prompts" / name).read_bytes()).hexdigest()
        for name in ("v2_initial_planner_v2.md", "search_agent_v2.md")
    }
    from researchassistant.contracts.query_planning import (
        V2AdaptiveSearchConceptsOutput,
        V2InitialPlannerConceptsOutput,
    )

    schema_hash = discovery_hash(
        json.dumps(
            {
                "foundation": binding.prompt_schema_hash,
                "prompts": prompt_hashes,
                "schemas": [
                    V2InitialPlannerConceptsOutput.model_json_schema(),
                    V2AdaptiveSearchConceptsOutput.model_json_schema(),
                ],
            },
            sort_keys=True,
        )
    )
    binding = binding.model_copy(
        update={"compiler_identity": QUERY_COMPILER_ID, "prompt_schema_hash": schema_hash}
    )
    bind_discovery_run(path, binding, clock())
    return binding


def query_provider_budgets(
    providers: tuple[DiscoveryProvider, ...],
    adapters: Mapping[DiscoveryProvider, SearchProvider],
    query_modes: Mapping[DiscoveryProvider, SearchMode] | None,
) -> tuple[V2DiscoveryProviderBudget, ...]:
    results = []
    for provider in providers:
        if provider not in _PROVIDER_CAPS:
            raise ValueError(f"unsupported compiled discovery provider: {provider.value}")
        mode = (query_modes or {}).get(
            provider, "provider_default" if provider is DiscoveryProvider.EXA else "lexical"
        )
        cost = _COSTS[provider]
        method = getattr(adapters[provider], "query_budget", None)
        configured = method(provider, mode) if callable(method) else None
        results.append(
            configured
            or V2DiscoveryProviderBudget(
                provider=provider,
                max_requests=_PROVIDER_CAPS[provider],
                max_cost_usd=cost * _PROVIDER_CAPS[provider],
                reservation_per_request_usd=cost,
                cost_basis="documented_free" if cost == 0 else "configured_upper_bound",
                cost_policy_identity=f"query-{provider.value}-{mode}-2026-10-06-v2",
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
        expected = {item.name: item.value for item in self.action.parameters}
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
                page_number=1,
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
                >= (
                    2
                    if request.provider is DiscoveryProvider.PUBMED and request_kind == "primary"
                    else 3
                )
                or actual is None
            ):
                return response

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
            return min(len(records), request.limit) if isinstance(records, list) else 0
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
    key = f"operation/{compiled_query.fingerprint}"
    operation = V2DiscoveryOperation(
        run_id=run_id,
        artifact_id=discovery_id(run_id, "V2DiscoveryOperation", key),
        identity_key=key,
        binding_fingerprint=binding.fingerprint,
        action=compiled_query,
        created_at=clock(),
    )
    insert_discovery_operation(path, operation, operation.created_at)
    audit = provider_attempt_audit(path, run_id)
    if any(start.operation_id == compiled_query.artifact_id for start in audit.starts):
        raise SearchProviderError(
            SearchFailureCode.PERMANENT_FAILURE,
            "a started operation cannot be replayed; require a fresh run",
        )
    request = SearchRequest(
        run_id=run_id,
        provider=provider,
        intent=intent,
        semantic=compiled_query.mode == "semantic",
        query_text=compiled_query.query_text,
        limit=compiled_query.effective_depth,
        compiled_query=compiled_query,
    )
    observer = _PhysicalExecution(path, compiled_query, binding, clock, cancellation_requested)
    with observe_physical_requests(observer):
        if getattr(adapter, "physical_accounting", False):
            response = adapter.search(request)
            if observer.sequence == 0:
                raise SearchProviderError(
                    SearchFailureCode.PERMANENT_FAILURE,
                    "adapter omitted required physical request accounting",
                )
            return response
        # Injected fake/third-party one-request adapters still receive durable accounting.
        if provider is DiscoveryProvider.PUBMED:
            raise SearchProviderError(
                SearchFailureCode.PERMANENT_FAILURE,
                "PubMed adapter must expose both physical metadata requests",
            )
        result: SearchResponse | None = None

        def send() -> httpx.Response:
            nonlocal result
            result = adapter.search(request)
            body: dict[str, object] = {
                "results": [x.model_dump(mode="json") for x in result.results]
            }
            if result.cost_usd is not None:
                if provider is DiscoveryProvider.EXA:
                    body["costDollars"] = {"total": str(result.cost_usd)}
                else:
                    body["meta"] = {"cost_usd": str(result.cost_usd)}
            return httpx.Response(200, json=body)

        observer.request(
            request,
            {x.name: x.value for x in compiled_query.parameters},
            send,
            request_kind="primary",
        )
        if result is None:
            raise RuntimeError("query execution omitted its response")
        return result
