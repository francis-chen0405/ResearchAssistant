"""Run the current production CLI in a fresh process with offline provider fixtures."""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend/src"))
sys.path.insert(0, str(Path(__file__).parent))

from test_pipeline_selection import _environment  # noqa: E402
from test_query_production import _ConceptModel  # noqa: E402
from test_v2_phase12_production import _Scraper, _Search  # noqa: E402

import researchassistant.runtime.cli as cli  # noqa: E402
from providers.llm import LLMRequest  # noqa: E402
from providers.v2_factory import V2ProductionFactoryConfig  # noqa: E402
from researchassistant.storage.store import read_cancellation_request  # noqa: E402


def main() -> int:
    scenario = os.environ.get("MVP4_MOCK_SCENARIO", "released")

    class Model(_ConceptModel):
        def generate(self, request: LLMRequest) -> object:
            if scenario == "failed":
                raise RuntimeError("offline provider failure")
            if scenario == "second-process-cancel":
                database = os.environ["MVP4_DB_PATH"]
                run_id = UUID(os.environ["MVP4_RUN_ID"])
                deadline = time.monotonic() + 15
                while True:
                    try:
                        read_cancellation_request(database, run_id)
                    except KeyError:
                        if time.monotonic() >= deadline:
                            raise RuntimeError(
                                "timed out waiting for second-process cancellation"
                            ) from None
                        time.sleep(0.05)
                    else:
                        break
            return super().generate(request)

    search = _Search(unique_results=True)
    if scenario == "blocked":
        from datetime import datetime

        from researchassistant.agents import v2_final_output

        original_builder = v2_final_output.build_v2_synthesis_output

        def invalid_builder(*, synthesis_input: object, created_at: datetime) -> object:
            valid = original_builder(synthesis_input=synthesis_input, created_at=created_at)
            section = valid.sections[0]
            item = section.items[0].model_copy(
                update={"approved_factual_statement": "Unsupported altered statement."}
            )
            section = section.model_copy(update={"items": (item,)})
            return valid.model_copy(update={"sections": (section, *valid.sections[1:])})

        v2_final_output.build_v2_synthesis_output = invalid_builder

    def bundle(config: V2ProductionFactoryConfig) -> SimpleNamespace:
        return SimpleNamespace(
            llm=Model(completed_rounds=1),
            search_providers={provider: search for provider in config.discovery_providers},
            wigolo=_Scraper(),
            firecrawl=None,
        )

    cli.build_v2_production_bundle = bundle
    environment = dict(os.environ)
    environment.setdefault("LUNA_BASE_URL", "https://api.openai.com/v1")
    environment.setdefault("LUNA_MODEL", "gpt-6-luna")
    for key, value in _environment().items():
        if key not in {"MIMO_API_KEY", "EXA_API_KEY", "OPENALEX_API_KEY"}:
            environment.setdefault(key, value)
    cli.environ = environment
    return cli.main(
        identity_provider=lambda: os.environ.get(
            "MVP4_REPOSITORY_IDENTITY", "source-sha256:" + "a" * 64
        ),
    )


if __name__ == "__main__":
    raise SystemExit(main())
