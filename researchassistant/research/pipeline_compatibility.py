"""Typed compatibility boundaries for the historical provider pipeline."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol
from uuid import UUID

from providers.mimo_factory import MimoProviderFactoryConfig
from researchassistant.contracts.models import ResearchControls
from researchassistant.research.orchestrator import ProviderPipelineResult


class LegacyPipelineRunner(Protocol):
    """Callable boundary for explicitly selected historical pipeline runs."""

    def __call__(
        self,
        raw_claim: str,
        *,
        db_path: str | Path,
        factory_config: MimoProviderFactoryConfig,
        run_id: UUID,
        research_controls: ResearchControls,
    ) -> ProviderPipelineResult: ...
