"""Explicitly gated one-search/one-acquisition/one-LLM MVP-2B boundary smoke."""

from __future__ import annotations

import json
import os
import sys
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

from agents.reviewer import ReviewerDecision, ReviewerInput
from providers.acquisition import WigoloAcquisitionAdapter
from providers.config import LiveSmokeConfig, OpenRouterConfig, WigoloConfig
from providers.llm import LLMStage, ModelAlias, build_stage_request
from providers.openrouter import OpenRouterAdapter
from providers.scraper import ScrapeRequest
from providers.search import SearchRequest
from providers.wigolo import WigoloSearchAdapter

_APPROVAL_PHRASE = "I_APPROVE_ONE_MVP2B_LIVE_SMOKE"


def main() -> int:
    if sys.argv[1:] != ["--execute"]:
        raise RuntimeError("live smoke requires the exact --execute argument")
    output_path = Path(os.environ.get("RESEARCH_ASSISTANT_SMOKE_OUTPUT", ""))
    smoke = LiveSmokeConfig(
        enabled=os.environ.get("RESEARCH_ASSISTANT_LIVE_SMOKE") == "1",
        approved_now=os.environ.get("RESEARCH_ASSISTANT_LIVE_APPROVED") == _APPROVAL_PHRASE,
        max_search_calls=_required_int("RESEARCH_ASSISTANT_SMOKE_MAX_SEARCH_CALLS"),
        max_acquisition_calls=_required_int("RESEARCH_ASSISTANT_SMOKE_MAX_ACQUISITION_CALLS"),
        max_llm_calls=_required_int("RESEARCH_ASSISTANT_SMOKE_MAX_LLM_CALLS"),
        max_tokens=_required_int("RESEARCH_ASSISTANT_SMOKE_MAX_TOKENS"),
        max_cost_usd=Decimal(_required("RESEARCH_ASSISTANT_SMOKE_MAX_COST_USD")),
        output_path=output_path,
    )
    smoke.require_enabled()
    if smoke.output_path.exists():
        raise RuntimeError("dedicated smoke output must not already exist")

    wigolo_config = WigoloConfig()
    openrouter_config = OpenRouterConfig.from_environment(os.environ)
    search = WigoloSearchAdapter(wigolo_config)
    acquisition = WigoloAcquisitionAdapter(wigolo_config)
    llm = OpenRouterAdapter(
        openrouter_config,
        max_call_cost_usd=smoke.max_cost_usd,
        max_call_tokens=smoke.max_tokens,
    )

    search_response = search.search(
        SearchRequest(query_text="public evidence on reproducible research methods", limit=5)
    )
    source = acquisition.scrape(
        ScrapeRequest(
            url=search_response.results[0].original_url,
            timeout_seconds=wigolo_config.deadlines.html_fetch_seconds,
        )
    )
    reviewer_input = ReviewerInput(
        extracted_quote_block=(
            '[Start of Text] "This is non-sensitive smoke-test text." [End of Text]'
        ),
        preceding_context="Start of Text",
        following_context="End of Text",
        draft_statement="This is non-sensitive smoke-test text.",
        claim_fit=3,
    )
    request = build_stage_request(
        stage=LLMStage.REVIEWER,
        input_artifact=reviewer_input,
        requested_output_type=ReviewerDecision,
        input_artifact_ids=(uuid4(),),
        model_alias=ModelAlias.MIMO_V25_PRO,
        run_id=uuid4(),
    )
    output = llm.generate(request)
    metadata = llm.last_call_metadata()
    report = {
        "calls": {"search": 1, "acquisition": 1, "llm": 1},
        "search_provider": search_response.provider_name,
        "search_provider_version": search_response.provider_version,
        "source_final_url": source.resolved_url,
        "source_content_type": source.content_type,
        "source_sha256": source.snapshot_sha256,
        "normalization_version": source.normalization_version,
        "llm_model": metadata.returned_model,
        "llm_upstream": metadata.upstream_provider,
        "usage": metadata.usage.model_dump(mode="json"),
        "cost_estimated": metadata.cost_estimated,
        "structured_output_type": type(output).__name__,
    }
    smoke.output_path.parent.mkdir(parents=True, exist_ok=True)
    smoke.output_path.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


def _required(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"{name} must be set explicitly")
    return value


def _required_int(name: str) -> int:
    try:
        return int(_required(name))
    except ValueError as exc:
        raise RuntimeError(f"{name} must be an integer") from exc


if __name__ == "__main__":
    raise SystemExit(main())
