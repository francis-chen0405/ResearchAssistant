"""Independent direction selection shared by research and discovery contracts."""

from __future__ import annotations

import json
from enum import StrEnum

from pydantic import ConfigDict, model_validator

from researchassistant.contracts.model_contracts import StrictModel


class ResearchDirection(StrEnum):
    SUPPORT = "support"
    CHALLENGE = "challenge"


class ResearchDirections(StrictModel):
    """The complete, independent direction selection for a fresh v2 run."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    support_enabled: bool = True
    challenge_enabled: bool = False

    @model_validator(mode="after")
    def validate_at_least_one_enabled(self) -> ResearchDirections:
        if not self.support_enabled and not self.challenge_enabled:
            raise ValueError("at least one research direction must be enabled")
        return self

    @property
    def enabled_directions(self) -> tuple[ResearchDirection, ...]:
        return tuple(
            direction
            for direction, enabled in (
                (ResearchDirection.SUPPORT, self.support_enabled),
                (ResearchDirection.CHALLENGE, self.challenge_enabled),
            )
            if enabled
        )

    def permits(self, direction: ResearchDirection) -> bool:
        return direction in self.enabled_directions

    def require_permitted(self, direction: ResearchDirection) -> None:
        if not self.permits(direction):
            raise ValueError(
                f"disabled research direction cannot appear in a v2 artifact: {direction}"
            )

    def canonical_json(self) -> str:
        return json.dumps(self.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
