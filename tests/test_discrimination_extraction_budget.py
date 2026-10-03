from datetime import UTC, datetime
from hashlib import sha256
from uuid import UUID, uuid4

from agents.v2_extraction import V2ExtractionState, _extract_source
from providers.llm import LLMProviderCapabilities, LLMRequest
from providers.v2_budget import V2BudgetExceededError, V2SourceBudgetExceededError
from researchassistant.contracts.models import (
    ResearchDirection,
    SourceSnapshot,
    V2VerbatimQuoteSelection,
)

NOW = datetime(2026, 10, 2, tzinfo=UTC)
PASSAGE = (
    "Among the participants in the regional program, 62 percent completed the course "
    "within six months compared with 48 percent of matched adults receiving standard "
    "materials during the same observation period."
)


class ExtractionProvider:
    capabilities = LLMProviderCapabilities(
        supports_temperature=True, supports_structured_output_control=True
    )

    def __init__(self, failure: Exception | None = None) -> None:
        self.failure = failure
        self.requests: list[LLMRequest] = []

    def generate(self, request: LLMRequest) -> V2VerbatimQuoteSelection:
        self.requests.append(request)
        if self.failure is not None:
            raise self.failure
        return V2VerbatimQuoteSelection(
            selected_sentence_ranges=({"start_sentence": 2, "end_sentence": 2},)
        )


def snapshot() -> SourceSnapshot:
    text = f"Opening context. {PASSAGE} Closing context."
    return SourceSnapshot(
        run_id=uuid4(),
        snapshot_id=uuid4(),
        retrieval_attempt_id=uuid4(),
        source_url="https://example.test/evaluation",
        retrieved_at=NOW,
        normalized_text=text,
        snapshot_sha256=sha256(text.encode()).hexdigest(),
        word_count=len(text.split()),
        truncated=False,
        normalization_version="fixture-v1",
        created_at=NOW,
    )


def extract(provider: ExtractionProvider, source_id: UUID) -> V2ExtractionState:
    result = _extract_source(
        source_id=source_id,
        direction=ResearchDirection.SUPPORT,
        exact_claim="The course helps completion.",
        snapshot=snapshot(),
        query_id=uuid4(),
        query_round=1,
        search_rank=1,
        llm_provider=provider,
        clock=lambda: NOW,
    )
    return result.state


def test_full_extraction_context_is_rendered_once_and_exact_quote_survives() -> None:
    provider = ExtractionProvider()
    assert extract(provider, uuid4()) is V2ExtractionState.EXTRACTED
    rendered = provider.requests[0].rendered_prompt
    assert rendered.count(PASSAGE) == 1
    assert "Opening context." in rendered and "Closing context." in rendered
    assert "UNTRUSTED_SOURCE_TEXT" in rendered
    artifact = provider.requests[0].input_artifact
    assert artifact.untrusted_source_text == f"Opening context. {PASSAGE} Closing context."
    assert "[2] " + PASSAGE in artifact.selectable_source_text


def test_budget_preflight_failure_is_not_retried_or_reported_as_extraction_failure() -> None:
    provider = ExtractionProvider(
        V2BudgetExceededError("v2 total-token ceiling cannot cover this call")
    )
    state = extract(provider, uuid4())
    assert state.value == "budget_exhausted"
    assert len(provider.requests) == 1


def test_source_cap_block_is_distinct_and_not_retried() -> None:
    source_id = uuid4()
    provider = ExtractionProvider(
        V2SourceBudgetExceededError(f"source {source_id} token cap cannot cover this call")
    )
    assert extract(provider, source_id).value == "source_budget_blocked"
    assert len(provider.requests) == 1
