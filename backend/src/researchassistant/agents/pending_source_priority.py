"""A frozen, bounded scheduling preference; never an evidence or admission score."""

from __future__ import annotations

import re
from collections import Counter
from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import ConfigDict

from researchassistant.agents.v2_source_selection import _candidate_sort_key
from researchassistant.agents.v2_stage_checkpoint import checkpoint_hash, read_checkpoint
from researchassistant.contracts.models import (
    StrictModel,
    V2ClaimCoverageState,
    V2GapAnalysisOutput,
    V2GapAnalysisState,
    V2SourceSelectionCandidate,
    V2SourceSelectionQueueResult,
)
from researchassistant.storage.store import insert_v2_artifact

_WORDS = re.compile(r"[^\W\d_]+", re.UNICODE)
_GENERIC = frozenset(
    "a an and are as at be been by claim comparison data does effect effects evidence for "
    "from has have in independent is it material missing more of on or outcome outcomes "
    "measured measurement partial research result results source sources study studies "
    "than that the their this "
    "to unresolved was were with without".split()
)


class V2PendingSourcePriority(StrictModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: UUID
    policy: Literal["pending-gap-preference-v1"] = "pending-gap-preference-v1"
    input_sha256: str
    baseline: tuple[UUID, ...]
    ordered: tuple[UUID, ...]
    promising: tuple[UUID, ...]


def _phrases(text: str) -> frozenset[tuple[str, str]]:
    """Require two adjacent, distinct, non-generic words of at least four letters.

    Do not stem, expand synonyms, join passages, or use query/rationale metadata.
    This intentionally misses single-word and paraphrased leads.
    """
    normalized = text.casefold()
    words = tuple(_WORDS.finditer(normalized))
    return frozenset(
        (a.group(), b.group())
        for a, b in zip(words, words[1:], strict=False)
        if a.group() != b.group()
        and len(a.group()) >= 4
        and len(b.group()) >= 4
        and a.group() not in _GENERIC
        and b.group() not in _GENERIC
        and normalized[a.end() : b.start()].isspace()
    )


def _can_precede(a: V2SourceSelectionCandidate, b: V2SourceSelectionCandidate) -> bool:
    # Missing type is unknown, not a fabricated low quality value. Reuse the
    # existing type priority; compare only completed current 0–100 previews.
    if not a.source_type or not b.source_type:
        return False
    if _candidate_sort_key(a)[1] > _candidate_sort_key(b)[1]:
        return False
    previews = (a.preview, b.preview)
    if any(
        p is None
        or p.request.preview_identity != "source-claim-preview-v2"
        or p.outcome != "completed"
        or p.capture_usable is not True
        or "relevance_score" not in p.model_fields_set
        for p in previews
    ):
        return False
    return a.preview.relevance_score >= b.preview.relevance_score - 5


def bounded_pending_order(
    queue: V2SourceSelectionQueueResult,
    baseline: tuple[UUID, ...],
    promising: frozenset[UUID],
) -> tuple[UUID, ...]:
    """Rebuild from the original pending baseline, with at most two slots of motion.

    Exchange only equal direction/recommendation/family-occurrence slots. Preserve
    sibling order and every existing type/relevance precedence on inverted pairs.
    Equal preference retains baseline order, including independent confirmation.
    """
    candidates = {c.source_id: c for c in queue.input.survivors}
    recommended = set(queue.recommended_source_ids)
    positions = {sid: i for i, sid in enumerate(baseline)}
    occurrences: Counter[tuple[object, str]] = Counter()
    partitions = {}
    for sid in baseline:
        c = candidates[sid]
        family = (c.direction, c.source_family_id)
        partitions[sid] = (c.direction, sid in recommended, occurrences[family])
        occurrences[family] += 1
    ordered = list(baseline)
    for sid in baseline:
        if sid not in promising:
            continue
        j = ordered.index(sid)
        for i in range(max(0, positions[sid] - 2), j):
            displaced = ordered[i]
            if partitions[sid] != partitions[displaced]:
                continue
            slots = [k for k in range(i, j + 1) if partitions[ordered[k]] == partitions[sid]]
            if any(ordered[k] in promising for k in slots[:-1]):
                continue
            proposal = ordered.copy()
            for target, source in zip(slots[1:], slots[:-1], strict=True):
                proposal[target] = ordered[source]
            proposal[i] = sid
            if any(abs(k - positions[x]) > 2 for k, x in enumerate(proposal)):
                continue
            # Keep family member order exactly, even after removal of earlier work.
            if any(
                [x for x in proposal if candidates[x].source_family_id == family]
                != [x for x in baseline if candidates[x].source_family_id == family]
                for family in {candidates[x].source_family_id for x in ordered[i : j + 1]}
            ):
                continue
            if any(
                positions[a] > positions[b] and not _can_precede(candidates[a], candidates[b])
                for k, a in enumerate(proposal)
                for b in proposal[k + 1 :]
            ):
                continue
            ordered = proposal
            break
    return tuple(ordered)


def freeze_pending_priority(
    *,
    path: str,
    key: str,
    queue: V2SourceSelectionQueueResult,
    baseline: tuple[UUID, ...],
    gap_outputs: tuple[V2GapAnalysisOutput, ...],
    already_started: bool,
    now: datetime,
) -> tuple[UUID, ...]:
    """Freeze once before dispatch; waves consume this decision without boosting again.

    No new Gap Analysis is completed within final analysis waves. Removing a
    dispatched prefix only shrinks displacement relative to the remaining baseline.
    Resume reads the saved decision, never later physical completion order.
    """
    # Invocation wrappers carry transient resumed/invocation fields. Bind only
    # the validated persisted contract, identically before and after restart.
    queue = V2SourceSelectionQueueResult.model_validate(
        queue.model_dump(include=set(V2SourceSelectionQueueResult.model_fields))
    )
    gap_outputs = tuple(
        V2GapAnalysisOutput.model_validate(
            output.model_dump(include=set(V2GapAnalysisOutput.model_fields))
        )
        for output in gap_outputs
    )
    for output in gap_outputs:
        if (
            output.run_id != queue.run_id
            or output.input.exact_claim != queue.input.exact_claim
            or output.input.directions != queue.input.directions
            or output.result is not None
            and output.result.directions != queue.input.directions
        ):
            raise ValueError("pending priority Gap assessment belongs to another investigation")
    completed = tuple(o for o in gap_outputs if o.state is V2GapAnalysisState.COMPLETED)
    latest = max(
        completed,
        key=lambda o: (
            o.input.completed_round,
            o.completed_at,
            checkpoint_hash(o.model_dump(mode="json")),
        ),
        default=None,
    )
    latest_hashes = sorted(
        {
            checkpoint_hash(o.model_dump(mode="json"))
            for o in completed
            if latest is not None
            and (o.input.completed_round, o.completed_at)
            == (latest.input.completed_round, latest.completed_at)
        }
    )
    if len(latest_hashes) > 1:
        latest = None  # Conflicting same-time assessments have no established latest owner.
    identity = checkpoint_hash(
        {
            "queue": queue.model_dump(mode="json"),
            "baseline": tuple(map(str, baseline)),
            "latest_gap": latest.model_dump(mode="json") if latest else None,
            "latest_assessment_hashes": latest_hashes,
        }
    )
    saved = read_checkpoint(path, queue.run_id, key, V2PendingSourcePriority)
    if saved is not None:
        if saved.input_sha256 != identity or saved.baseline != baseline:
            raise ValueError("saved pending priority input changed")
        if (
            saved.run_id != queue.run_id
            or len(saved.ordered) != len(baseline)
            or set(saved.ordered) != set(baseline)
            or any(abs(i - baseline.index(sid)) > 2 for i, sid in enumerate(saved.ordered))
        ):
            raise ValueError("invalid saved pending priority decision")
        return saved.ordered
    phrases: set[tuple[str, str]] = set()
    if latest is not None and latest.result is not None and not already_started:
        coverage = latest.result.claim_coverage_map
        for gap in latest.result.material_gaps:
            if (
                gap.claim_dimension is None
                or sum(
                    c.dimension == gap.claim_dimension
                    and c.claim_component == gap.unsupported_claim_component
                    and c.searchable
                    and c.coverage_state
                    in {
                        V2ClaimCoverageState.MISSING,
                        V2ClaimCoverageState.PARTIAL,
                        V2ClaimCoverageState.CONFLICTING,
                    }
                    for c in coverage
                )
                != 1
                or sum(c.dimension == gap.claim_dimension for c in coverage) != 1
            ):
                continue
            phrases.update(_phrases(gap.missing_evidence))
    phrases.difference_update(_phrases(queue.input.exact_claim))
    # Gap direction is deliberately absent: it is search provenance, not stance.
    promising = frozenset(
        c.source_id
        for c in queue.input.survivors
        if c.source_id in baseline
        and c.preview is not None
        and c.preview.request.preview_identity == "source-claim-preview-v2"
        and c.preview.outcome == "completed"
        and c.preview.capture_usable is True
        and any(
            phrases.intersection(_phrases(span.text))
            for span in c.preview.spans
            if span.section not in {"title", "bibliography"}
        )
    )
    ordered = bounded_pending_order(queue, baseline, promising)
    insert_v2_artifact(
        path,
        key,
        V2PendingSourcePriority(
            run_id=queue.run_id,
            input_sha256=identity,
            baseline=baseline,
            ordered=ordered,
            promising=tuple(x for x in baseline if x in promising),
        ),
        now,
    )
    return ordered
