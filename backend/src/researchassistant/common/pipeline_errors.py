"""Shared compatibility failures; importing them does not select an executor."""

from __future__ import annotations

from researchassistant.contracts.model_contracts import Stage


class Phase9OrchestrationError(RuntimeError):
    """Explicit Phase 9 failure carrying the stage that could not complete."""

    def __init__(self, stage: Stage, message: str) -> None:
        super().__init__(message)
        self.stage = stage


class ClaimMismatchError(ValueError):
    """A persisted run ID was reused with a different authoritative claim."""


class FingerprintMismatchError(ValueError):
    """A persisted run ID was reused with an incompatible provider contract."""
