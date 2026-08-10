"""Subprocess entry point that runs the production CLI with mocked provider HTTP."""

from __future__ import annotations

import os
import runpy
import sys
import time
from decimal import Decimal
from hashlib import sha256
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import cli  # noqa: E402
from models import ProviderRunContract  # noqa: E402
from provider_contract import canonical_provider_contract_payload  # noqa: E402
from providers.llm import DEFAULT_LLM_ROUTING  # noqa: E402
from store import read_cancellation_request  # noqa: E402


def _load_provider_test_helpers() -> dict[str, object]:
    return runpy.run_path(str(Path(__file__).with_name("test_phase9.py")))


def main() -> int:
    helpers = _load_provider_test_helpers()
    llm_type = helpers["FakeLLMProvider"]
    search_type = helpers["FakeSearchProvider"]
    scraper_type = helpers["FakeScraperProvider"]
    run_pipeline = helpers["run_provider_pipeline"]
    now = helpers["NOW"]
    scenario = os.environ.get("MVP4_MOCK_SCENARIO", "released")
    llm_kwargs: dict[str, object] = {}
    if scenario == "blocked":
        llm_kwargs["invalidate_synthesis"] = True
    elif scenario == "failed":
        llm_kwargs["transient_failures"] = {
            (helpers["LLMStage"].PLANNER, helpers["ModelAlias"].MIMO_V25_PRO): 3,
            (helpers["LLMStage"].PLANNER, helpers["ModelAlias"].MINIMAX_M3): 3,
        }
    elif scenario == "second-process-cancel":
        db_path = Path(os.environ["MVP4_DB_PATH"])
        run_id = os.environ["MVP4_RUN_ID"]

        def wait_for_cancellation() -> None:
            deadline = time.monotonic() + 15
            while time.monotonic() < deadline:
                try:
                    read_cancellation_request(str(db_path), helpers["UUID"](run_id))
                except KeyError:
                    time.sleep(0.05)
                    continue
                return
            raise RuntimeError("timed out waiting for second-process cancellation")

    llm_kwargs["usage"] = helpers["ModelUsageMetadata"](
        total_tokens=15,
        cost_usd=Decimal("0.0001"),
    )
    if scenario == "second-process-cancel":

        class CancellationAwareLLM(llm_type):
            def generate(self, request: object) -> object:
                wait_for_cancellation()
                return super().generate(request)

        llm = CancellationAwareLLM(**llm_kwargs)
    else:
        llm = llm_type(**llm_kwargs)

    def mocked_runner(*args: object, **kwargs: object) -> object:
        factory_config = kwargs["factory_config"]
        budget = helpers["OrchestrationBudget"](
            max_model_calls=factory_config.ceilings.max_llm_calls,
            retrieval_attempts_per_side=factory_config.acquisition.maximum_attempts_per_stance,
            max_total_tokens=factory_config.ceilings.max_tokens,
            max_total_cost_usd=factory_config.ceilings.max_cost_usd,
        )
        config = helpers["ProviderOrchestrationConfig"](
            routing=DEFAULT_LLM_ROUTING,
            acquisition_policy=factory_config.acquisition,
            budget=budget,
            require_budget_reservations=True,
            reserved_output_tokens_per_call=factory_config.mimo.max_completion_tokens,
            pricing_policy="compatibility",
        )
        payload_json = canonical_provider_contract_payload(
            {
                "fingerprint_version": "mvp7.1-subprocess-fixture-v1",
                "provider_identity": "mocked-direct-mimo",
                "adapter_identity": "mocked-direct-mimo-v1",
                "model_identity": "mimo-v2.5-pro",
                "prompt_identity": "mocked-prompts-v1",
                "schema_identity": "mocked-schemas-v1",
                "normalization_identity": "mocked-normalization-v1",
                "policy_identity": (
                    f"tokens:{factory_config.ceilings.max_tokens}|"
                    f"cost:{factory_config.ceilings.max_cost_usd}"
                ),
                "repository_revision": factory_config.repository_revision,
            }
        )
        contract = ProviderRunContract(
            run_id=kwargs["run_id"],
            fingerprint_sha256=sha256(payload_json.encode("utf-8")).hexdigest(),
            provider_identity="mocked-direct-mimo",
            adapter_identity="mocked-direct-mimo-v1",
            model_identity="mimo-v2.5-pro",
            prompt_identity="mocked-prompts-v1",
            schema_identity="mocked-schemas-v1",
            normalization_identity="mocked-normalization-v1",
            policy_identity=(
                f"tokens:{factory_config.ceilings.max_tokens}|"
                f"cost:{factory_config.ceilings.max_cost_usd}"
            ),
            repository_revision=factory_config.repository_revision,
            payload_json=payload_json,
            created_at=now,
        )
        scraper = scraper_type()
        original_scrape = scraper.scrape

        def scrape(request: object) -> object:
            response = original_scrape(request)
            return response.model_copy(update={"text": f"{response.text} {request.url}"})

        scraper.scrape = scrape
        return run_pipeline(
            args[0],
            db_path=kwargs["db_path"],
            search_provider=search_type(),
            scraper_provider=scraper,
            llm_provider=llm,
            run_id=kwargs["run_id"],
            config=config,
            provider_contract=contract,
            clock=lambda: now,
        )

    cli.run_mvp3b_pipeline = mocked_runner
    cli.repository_identity = lambda: os.environ.get(
        "MVP4_REPOSITORY_IDENTITY", "source-sha256:" + "a" * 64
    )
    return cli.main()


if __name__ == "__main__":
    raise SystemExit(main())
