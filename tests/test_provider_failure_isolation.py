from pathlib import Path
from uuid import uuid4

import httpx
import pytest
from test_discovery_store import _init_run
from test_query_execution import CLAIM, DIRECTIONS, _action, _clock, _round_one_query

from researchassistant.contracts.models import DiscoveryProvider
from researchassistant.providers.config import SerpSearchConfig
from researchassistant.providers.search import SearchProviderError
from researchassistant.providers.serpsearch import SerpSearchAdapter
from researchassistant.providers.web_search import WebSearchAdapter, WebSearchConfig
from researchassistant.research.query_execution import (
    available_query_budgets,
    execute_query,
    freeze_query_execution,
)
from researchassistant.research.v2_orchestrator import _run_round_one_search
from researchassistant.storage.discovery_store import provider_attempt_audit


def test_serp_http_500_preserves_reservation_and_allows_brave_search(tmp_path: Path) -> None:
    path = str(tmp_path / "provider-failure.sqlite")
    run_id = uuid4()
    _init_run(Path(path), run_id)
    failed_provider = DiscoveryProvider.SERPSEARCH
    healthy_provider = DiscoveryProvider.BRAVE
    freeze_query_execution(
        path, run_id, CLAIM, DIRECTIONS, (failed_provider, healthy_provider), _clock()
    )
    sent: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        sent.append(request.url.host)
        if "brave" in request.url.host:
            return httpx.Response(
                200,
                json={"web": {"results": [{"title": "Study", "url": "https://example.org/study"}]}},
            )
        return httpx.Response(500, text="upstream error")

    serp_config = SerpSearchConfig(api_key="offline-key")
    clock = _clock()
    with httpx.Client(
        base_url=serp_config.base_url, transport=httpx.MockTransport(handler)
    ) as client:
        providers = {
            failed_provider: SerpSearchAdapter(serp_config, client=client),
            healthy_provider: WebSearchAdapter(
                WebSearchConfig(provider=healthy_provider, api_key="offline-key"), client=client
            ),
        }
        failed = _action(run_id, failed_provider)
        healthy = _action(run_id, healthy_provider)
        result = _run_round_one_search(
            path,
            (_round_one_query(failed), _round_one_query(healthy)),
            providers,
            None,
            clock,
        )
        assert not result.outcomes[0].succeeded
        assert "HTTP 500" in result.outcomes[0].failure_message
        assert result.outcomes[1].succeeded
        assert result.outcomes[1].results[0].original_url == "https://example.org/study"
        budgets = available_query_budgets(path, run_id)
        assert {budget.provider for budget in budgets} == {healthy_provider}
        assert budgets[0].remaining_calls > 0

        another = _action(run_id, failed_provider, term="another research question")
        with pytest.raises(SearchProviderError, match="unknown request outcome"):
            execute_query(
                path=path,
                run_id=run_id,
                provider=failed_provider,
                query_text=another.query_text,
                compiled_query=another,
                providers=providers,
                clock=clock,
            )

    audit = provider_attempt_audit(path, run_id)
    assert len(sent) == len(audit.starts) == 2
    receipts = {
        start.provider: (start, completion)
        for start, completion in zip(audit.starts, audit.completions, strict=True)
    }
    failed_start, failed_completion = receipts[failed_provider]
    _, healthy_completion = receipts[healthy_provider]
    assert failed_start.reserved_cost_usd > 0
    assert failed_completion.actual_cost_usd is None
    assert healthy_completion.status == "completed"
