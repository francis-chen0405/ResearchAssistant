"""Shared deterministic artifact persistence for fixture and historical execution."""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from typing import TYPE_CHECKING, TypeVar

from models import (
    PlannerOutput,
    StrictModel,
)

if TYPE_CHECKING:
    pass


_ModelT = TypeVar("_ModelT", bound=StrictModel)


class FixturePipelineError(RuntimeError):
    """Raised for malformed fixtures or unexpected fixture-pipeline failures."""


def _claim_keywords_from_planner(planner: PlannerOutput) -> tuple[str, ...]:
    text = " ".join(
        (
            planner.claim_definition.claim_text,
            planner.claim_definition.population,
            planner.claim_definition.intervention_or_exposure,
        )
    )
    stop_words = {
        "a",
        "an",
        "and",
        "are",
        "for",
        "in",
        "of",
        "or",
        "the",
        "to",
    }
    words = [word.strip(".,;:!?()[]{}\"'").casefold() for word in text.replace("-", " ").split()]
    keywords = tuple(
        dict.fromkeys(word for word in words if len(word) > 2 and word not in stop_words)
    )
    if not keywords:
        raise FixturePipelineError("PlannerOutput did not yield deterministic claim keywords")
    return keywords


def _persist_model(
    db_path: str,
    model: _ModelT,
    insert_fn: Callable[[str, _ModelT], None],
    read_existing: Callable[[], _ModelT],
    label: str,
) -> None:
    try:
        existing = read_existing()
    except KeyError:
        try:
            insert_fn(db_path, model)
        except sqlite3.IntegrityError as exc:
            raise FixturePipelineError(f"could not persist {label}: {exc}") from exc
        return
    _assert_same_model(existing, model, label)


def _assert_same_model(existing: StrictModel, expected: StrictModel, label: str) -> None:
    if existing.model_dump(mode="json") != expected.model_dump(mode="json"):
        raise FixturePipelineError(f"existing {label} differs from fixture artifact")
