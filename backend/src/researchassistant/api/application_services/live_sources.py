"""A bounded, read-only view of the evidence pipeline's live checkpoints."""

from __future__ import annotations

import re
import sqlite3
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from uuid import NAMESPACE_URL, UUID, uuid5

from pydantic import BaseModel

from researchassistant.agents.capture_overlap import V2CaptureDispatch, V2CaptureReady
from researchassistant.agents.v2_discovery import _normalized_doi, _provider_identity_anchors
from researchassistant.agents.v2_stage_checkpoint import (
    V2ScoutRoundCheckpoint,
    V2StageAttemptCheckpoint,
    V2StageOutcomeCheckpoint,
)
from researchassistant.contracts.acquisition_capture import (
    V2AcquisitionCaptureCompletion,
)
from researchassistant.contracts.artifact_keys import discovery_round_keys
from researchassistant.contracts.metadata_ranking import MetadataRank, V2MetadataRankingArtifact
from researchassistant.contracts.model_contracts import SourceSnapshot
from researchassistant.contracts.model_evidence import (
    V2EvidenceAdmissionRecord,
    V2EvidenceAdmissionSourceResult,
    V2EvidenceAnalystSourceResult,
    V2LedgerProvenance,
)
from researchassistant.contracts.paper_identity import V2PaperIdentityAudit
from researchassistant.contracts.research_acquisition import V2AcquisitionProbeOutput
from researchassistant.contracts.research_discovery import (
    NormalizedDiscoveryItem,
    ScoutBatch,
    ScoutItem,
    SourceCluster,
    V2DiscoveryScoutOutput,
    V2LateDiscoveryMirror,
)
from researchassistant.contracts.source_leads import LiveSourceCard, LiveSourcesPage
from researchassistant.evidence.paper_identity import paper_title_key
from researchassistant.storage.historical_decode import decode_v2_artifact
from researchassistant.storage.source_leads import (
    _MAX_ARTIFACTS,
    _MAX_BYTES,
    _TYPES,
    _key_matches,
    _same_run,
    _validate_capture_journal,
)
from researchassistant.storage.store import (
    _read_execute,
    _row_to_v2_artifact,
    open_read_only_store,
    read_run,
    read_snapshot_connection,
)

_FIRST_PASS = "/first-pass-v1"
_SCOUT_PLAN = "scout-checkpoint-v1/"
_BATCH_SIZE = 20
_ROUNDS = tuple(
    (number, discovery + suffix, f"phase-3-metadata-ranking-round-{number}{suffix}", probe)
    for number in range(1, 5)
    for discovery, probe in (discovery_round_keys(number),)
    for suffix in (_FIRST_PASS, "")
)
_KEYS: dict[str, type[BaseModel]] = {
    key: model
    for _, discovery, rank, probe in _ROUNDS
    for key, model in (
        (discovery, V2DiscoveryScoutOutput),
        (_SCOUT_PLAN + discovery, V2ScoutRoundCheckpoint),
        (rank, V2MetadataRankingArtifact),
        (probe, V2AcquisitionProbeOutput),
    )
}
_KEYS.update(
    {
        key: V2PaperIdentityAudit
        for key in ("retained-paper-identity-v1", "retained-paper-identity-v2")
    }
)
_PATTERNS = (
    *(f"{_SCOUT_PLAN}{discovery}/batch-%/attempt-%" for _, discovery, _, _ in _ROUNDS),
    *(
        discovery_round_keys(n)[1] + suffix
        for n in range(1, 5)
        for suffix in ("/captures/%", "/overlap-v1/dispatch-%", "/overlap-v1/ready/%")
    ),
    "phase-13-luna-evidence-analyst-source-%",
    "phase-13-evidence-admission-source-%",
)
_EXTRA_TYPES = {
    model.__name__: model
    for model in (
        V2StageAttemptCheckpoint,
        V2StageOutcomeCheckpoint,
        V2CaptureDispatch,
        V2CaptureReady,
    )
}


def _load(
    connection: sqlite3.Connection, run_id: UUID, known: str | None
) -> tuple[str, dict[str, BaseModel] | None]:
    # Check the latest relevant immutable row without opening payloads on idle polls.
    placeholders = ",".join("?" for _ in _KEYS)
    patterns = " OR ".join("artifact_key LIKE ?" for _ in _PATTERNS)
    inventory = (
        f"FROM v2_artifacts WHERE run_id = ? AND (artifact_key IN ({placeholders}) OR {patterns})"
    )
    parameters = (str(run_id), *_KEYS, *_PATTERNS)
    latest = _read_execute(connection, "SELECT MAX(rowid) " + inventory, parameters).fetchone()
    revision = str(latest[0] or 0)
    if revision == known:
        return revision, None
    rows = _read_execute(
        connection,
        "SELECT rowid, artifact_key, length(CAST(payload_json AS BLOB)) AS size "
        + inventory
        + " ORDER BY rowid LIMIT ?",
        (*parameters, _MAX_ARTIFACTS + 1),
    ).fetchall()
    if len(rows) > _MAX_ARTIFACTS or sum(row["size"] for row in rows) > _MAX_BYTES:
        raise sqlite3.IntegrityError("live sources exceed the bounded inspection inventory")
    values: dict[str, BaseModel] = {}
    for row in rows:
        full = _read_execute(
            connection, "SELECT * FROM v2_artifacts WHERE rowid = ?", (row["rowid"],)
        ).fetchone()
        envelope = _row_to_v2_artifact(full)
        key = row["artifact_key"]
        kind = _KEYS.get(key) or _EXTRA_TYPES.get(envelope.artifact_type)
        if kind is None:
            kind = _TYPES.get(envelope.artifact_type)
        if kind is None or envelope.artifact_type != kind.__name__:
            raise sqlite3.IntegrityError("live source checkpoint has an unexpected type")
        value = decode_v2_artifact(envelope, kind)
        _same_run(value, run_id)
        if key not in _KEYS and kind.__name__ not in _EXTRA_TYPES and not _key_matches(key, value):
            raise sqlite3.IntegrityError("live source checkpoint has an unexpected key")
        if isinstance(value, V2PaperIdentityAudit) and value.policy != key:
            raise sqlite3.IntegrityError("paper identity audit differs from its key")
        values[key] = value
    _validate_capture_journal(list(values.items()))
    return revision, values


def _scout_results(
    values: dict[str, BaseModel],
    plan_key: str,
    plan: V2ScoutRoundCheckpoint,
    batch_offset: int,
) -> dict[UUID, ScoutItem]:
    results = {}
    for key, outcome in values.items():
        if not key.startswith(plan_key + "/batch-") or not isinstance(
            outcome, V2StageOutcomeCheckpoint
        ):
            continue
        match = re.fullmatch(
            r"batch-([1-9][0-9]*)/attempt-([12])/outcome", key[len(plan_key) + 1 :]
        )
        if match is None:
            raise sqlite3.IntegrityError("live Scout outcome has an invalid key")
        batch, attempt_number = map(int, match.groups())
        attempt_key = key.removesuffix("/outcome")
        attempt = values.get(attempt_key)
        start = (batch - batch_offset - 1) * _BATCH_SIZE
        expected = plan.scout_item_ids[start : start + _BATCH_SIZE] if start >= 0 else ()
        if (
            not isinstance(attempt, V2StageAttemptCheckpoint)
            or attempt.stage_key != attempt_key.rsplit("/", 1)[0]
            or attempt.attempt_number != attempt_number
            or attempt.attempt_id
            != uuid5(NAMESPACE_URL, f"bounded-stage-v1::{plan.run_id}::{attempt_key}")
            or outcome.attempt_id != attempt.attempt_id
            or outcome.request_hash != attempt.request_hash
            or outcome.completed_at < attempt.started_at
            or not expected
        ):
            raise sqlite3.IntegrityError("live Scout outcome lacks its owning batch attempt")
        candidate = outcome.candidate
        if candidate is None:
            continue
        invocation = outcome.invocation
        if (
            not isinstance(candidate, ScoutBatch)
            or invocation is None
            or invocation.stage.value != "scout"
            or invocation.requested_output_type != "ScoutBatch"
            or invocation.input_artifact_ids != (plan.run_id, attempt.attempt_id)
            or invocation.started_at < attempt.started_at
            or invocation.ended_at > outcome.completed_at
            or {item.item_id for item in candidate.items} != set(expected)
            or any(item.item_id in results for item in candidate.items)
        ):
            raise sqlite3.IntegrityError("live Scout result differs from its saved batch")
        results.update((item.item_id, item) for item in candidate.items)
    return results


@dataclass(frozen=True)
class _Lead:
    item: NormalizedDiscoveryItem
    cluster: SourceCluster
    rank: MetadataRank | None
    scout: ScoutItem | None


def _round_leads(
    values: dict[str, BaseModel],
) -> Iterator[tuple[list[_Lead], tuple[V2LateDiscoveryMirror, ...]]]:
    prefix_batches = 0
    for number, discovery_key, rank_key, _ in _ROUNDS:
        first_pass = discovery_key.endswith(_FIRST_PASS)
        if first_pass:
            prefix_batches = 0
        plan_key = _SCOUT_PLAN + discovery_key
        plan = values.get(plan_key)
        discovery = values.get(discovery_key)
        ranking = values.get(rank_key)
        mirrors = ()
        if isinstance(discovery, V2DiscoveryScoutOutput):
            items, clusters = discovery.items, discovery.clusters
            scout = {
                item.item_id: item
                for batch, audit in zip(
                    discovery.scout_batches, discovery.scout_audits, strict=True
                )
                if not audit.fallback_used
                for item in batch.items
            }
            mirrors = discovery.late_mirrors
            if first_pass:
                prefix_batches = len(discovery.scout_batches)
        elif isinstance(plan, V2ScoutRoundCheckpoint):
            items, clusters = plan.items, plan.clusters
            ranking = plan.ranking_artifact
            scout = _scout_results(values, plan_key, plan, prefix_batches)
        else:
            continue
        by_item = {item_id: cluster for cluster in clusters for item_id in cluster.item_ids}
        item_ids = {item.item_id for item in items}
        ranks = {}
        if isinstance(ranking, V2MetadataRankingArtifact):
            ranks = {rank.item_id: rank for rank in ranking.ranks}
            if ranking.round_number != number or set(ranks) != item_ids:
                raise sqlite3.IntegrityError("live ranking differs from its saved pool")
        if (
            any(item.round_number != number for item in items)
            or set(by_item) != item_ids
            or sum(len(cluster.item_ids) for cluster in clusters) != len(item_ids)
            or not scout.keys() <= item_ids
        ):
            raise sqlite3.IntegrityError("live source pool membership differs")
        yield (
            [
                _Lead(item, by_item[item.item_id], ranks.get(item.item_id), scout.get(item.item_id))
                for item in items
            ],
            mirrors,
        )


def _ranked_identity(
    members: list[NormalizedDiscoveryItem],
) -> tuple[str, str, frozenset[tuple[str, str]]] | None:
    titles = {title for member in members if (title := paper_title_key(member.title))}
    dois = {
        doi for member in members if (doi := _normalized_doi(member.doi, exact_identifiers=True))
    }
    if len(titles) > 1 or len(dois) > 1:
        return None
    title, doi = next(iter(titles), ""), next(iter(dois), "")
    if doi:
        # The acquisition exclusion also needs a substantive, matching title
        # to treat a reused DOI as the same publication across rounds.
        return (title, doi, frozenset()) if len(title) >= 24 else None
    anchors = frozenset(
        anchor for member in members for anchor in _provider_identity_anchors(member)
    )
    if len({provider for provider, _ in anchors}) != len(anchors):
        return None
    return title, doi, anchors


def _group_leads(
    values: dict[str, BaseModel], captures: dict[UUID, list[SourceSnapshot]]
) -> list[list[_Lead]]:
    # Preserve the earliest saved member as the UI identity when later
    # checkpoints establish another location for the same work.
    parents: dict[UUID, UUID] = {}
    order: dict[UUID, int] = {}
    cluster_owners: dict[UUID, UUID] = {}
    leads: list[_Lead] = []

    def root(item_id: UUID) -> UUID:
        while parents[item_id] != item_id:
            parents[item_id] = parents[parents[item_id]]
            item_id = parents[item_id]
        return item_id

    def join(left: UUID, right: UUID) -> None:
        older, newer = sorted((root(left), root(right)), key=order.__getitem__)
        parents[newer] = older

    for pool, mirrors in _round_leads(values):
        for lead in pool:
            item_id = lead.item.item_id
            if item_id not in parents:
                parents[item_id] = item_id
                order[item_id] = len(order)
            join(item_id, cluster_owners.setdefault(lead.cluster.cluster_id, item_id))
            leads.append(lead)
        for mirror in mirrors:
            join(mirror.item_id, mirror.scouted_item_id)
    for value in values.values():
        if not isinstance(value, V2PaperIdentityAudit):
            continue
        for group in value.groups:
            confirmed = [
                cluster_owners[location.source_id]
                for location in group.locations
                if location.source_id in cluster_owners
                and any(
                    (snapshot.snapshot_id, snapshot.snapshot_sha256, snapshot.source_url)
                    == (location.snapshot_id, location.snapshot_hash, location.source_url)
                    for snapshot in captures.get(location.source_id, ())
                )
            ]
            for item_id in confirmed[1:]:
                join(confirmed[0], item_id)
    # Resolve explicit ownership first. Every rank-based link must agree
    # with the identity of both whole components, so an ambiguous member
    # cannot bridge conflicting works through another saved key.
    members: dict[UUID, list[NormalizedDiscoveryItem]] = {}
    for lead in leads:
        members.setdefault(root(lead.item.item_id), []).append(lead.item)
    identities = {owner: _ranked_identity(items) for owner, items in members.items()}
    work_owners: dict[tuple[str, str, str, frozenset[tuple[str, str]]], UUID] = {}
    for lead in leads:
        owner = root(lead.item.item_id)
        identity = identities[owner]
        if identity is None or lead.rank is None:
            continue
        title, doi, anchors = identity
        if lead.rank.work_key.startswith("doi:") and not doi:
            continue
        key = (lead.rank.work_key, title, doi, anchors)
        join(owner, work_owners.setdefault(key, owner))

    groups: dict[UUID, list[_Lead]] = {}
    for lead in leads:
        groups.setdefault(root(lead.item.item_id), []).append(lead)
    return list(groups.values())


def _captures(
    values: dict[str, BaseModel],
) -> tuple[dict[UUID, list[SourceSnapshot]], set[UUID]]:
    captures: dict[UUID, list[SourceSnapshot]] = {}
    full_text: set[UUID] = set()
    dispatches: dict[tuple[str, UUID], V2CaptureDispatch] = {}
    for key, value in values.items():
        if isinstance(value, V2CaptureDispatch):
            prefix = key.rsplit("/", 1)[0]
            dispatches[(prefix, value.cluster_id)] = value

    for key, value in values.items():
        if isinstance(value, V2AcquisitionCaptureCompletion) and value.readable and value.source:
            captures.setdefault(value.source.cluster_id, []).append(value.source.snapshot)
        if isinstance(value, V2CaptureReady):
            prefix, _, cluster = key.rsplit("/", 2)
            if (
                cluster != str(value.dispatch.cluster_id)
                or dispatches.get((prefix, value.dispatch.cluster_id)) != value.dispatch
            ):
                raise sqlite3.IntegrityError("live ready capture differs from its dispatch")
            value = value.output
        if isinstance(value, V2AcquisitionProbeOutput):
            probes = {probe.snapshot_id: probe for probe in value.probes}
            for acquired in value.acquisitions:
                snapshot = acquired.snapshot
                probe = probes[snapshot.snapshot_id]
                preview = probe.preview
                if (
                    (preview.capture_usable if preview else None)
                    or (preview is None or preview.capture_usable is None)
                    and probe.succeeded
                ):
                    captures.setdefault(acquired.cluster_id, []).append(snapshot)
                    if preview and preview.content_classification == "full_text":
                        full_text.add(snapshot.snapshot_id)
    return captures, full_text


def _admissions(connection: sqlite3.Connection, values: dict[str, BaseModel]) -> set[UUID]:
    admitted = set()
    for result in values.values():
        if not isinstance(result, V2EvidenceAdmissionSourceResult) or not result.evidence_record:
            continue
        record = result.evidence_record
        row = _read_execute(
            connection,
            "SELECT ledger_record_json, provenance_json FROM v2_ledger_admissions "
            "WHERE run_id = ? AND ledger_claim_id = ?",
            (str(result.run_id), str(record.ledger_claim_id)),
        ).fetchone()
        if (
            row is None
            or V2EvidenceAdmissionRecord.model_validate_json(row["ledger_record_json"]) != record
            or V2LedgerProvenance.model_validate_json(row["provenance_json"]) != result.provenance
        ):
            raise sqlite3.IntegrityError("live admission differs from its evidence ledger row")
        admitted.add(result.source_id)
    return admitted


_METHODS = {
    "systematic-review": "Systematic review",
    "meta-analysis": "Meta-analysis",
    "randomized-controlled-trial": "Randomized trial",
    "clinical-trial": "Clinical trial",
    "observational-study": "Observational study",
    "cohort-study": "Cohort study",
    "case-control-study": "Case-control study",
    "qualitative-study": "Qualitative study",
}


def _method(item: NormalizedDiscoveryItem) -> str | None:
    return _METHODS.get(re.sub(r"[ _]+", "-", (item.source_type or "").strip().casefold()))


@dataclass(frozen=True)
class _Work:
    card: LiveSourceCard
    merit: float
    promising: bool
    method: str | None
    relationship: str | None


def _metadata_score(lead: _Lead) -> float:
    if lead.rank is None:
        return 0.0
    return lead.rank.score


def _work(
    group: list[_Lead],
    captures: dict[UUID, list[SourceSnapshot]],
    full_text: set[UUID],
    analysis: dict[UUID, V2EvidenceAnalystSourceResult],
    admitted: set[UUID],
) -> _Work:
    # The final plan may revise ranks for existing items while the prefix is
    # still the only checkpoint that can supply their Scout decisions.
    latest = {lead.item.item_id: lead for lead in group}
    best = max(latest.values(), key=_metadata_score)
    score = _metadata_score(best)
    directness = (best.rank.directness or 0.0) if best.rank else 0.0
    decisions = {lead.item.item_id: lead.scout for lead in group if lead.scout is not None}
    screened = next(
        (decision for decision in decisions.values() if decision.decision == "retrieve"),
        next((decision for decision in decisions.values() if decision.decision == "maybe"), None),
    )
    clusters = tuple(dict.fromkeys(lead.cluster.cluster_id for lead in group))
    snapshots = [snapshot for cluster in clusters for snapshot in captures.get(cluster, ())]
    assessed = max(
        (
            result.assessment
            for cluster in clusters
            if (result := analysis.get(cluster)) is not None and result.assessment is not None
        ),
        key=lambda assessment: (assessment.claim_fit, assessment.evidence_quality),
        default=None,
    )
    in_ledger = any(cluster in admitted for cluster in clusters)
    promising = in_ledger or (
        assessed.claim_fit >= 3 and assessed.evidence_quality >= 3
        if assessed
        else (not decisions or screened is not None)
        and (
            directness >= 0.30
            and score >= 0.48
            or screened is not None
            and screened.decision == "retrieve"
            and directness >= 0.20
        )
    )
    item = best.item
    state = "lead"
    note, note_kind = item.snippet or item.abstract, "metadata"
    if decisions:
        state = "screened"
        note, note_kind = (screened or next(iter(decisions.values()))).rationale, "scout"
    readable = min(
        snapshots,
        key=lambda snapshot: (snapshot.snapshot_id not in full_text, snapshot.truncated),
        default=None,
    )
    if readable:
        state = "full_text" if readable.snapshot_id in full_text else "captured"
    relationship = None
    if assessed:
        state = "assessed"
        note, note_kind = assessed.reasoning, "analyst"
        if assessed.claim_fit >= 3 and assessed.evidence_quality >= 3:
            relationship = assessed.relationship_to_claim.value
            score = 0.55 * score + 0.45 * (assessed.claim_fit + assessed.evidence_quality) / 10
    if in_ledger:
        state = "admitted"
    merit = score + (0.06 if screened and screened.decision == "retrieve" else 0)
    merit += (0.04 if snapshots else 0) + (0.06 if in_ledger else 0)
    method = next((method for lead in latest.values() if (method := _method(lead.item))), None)
    return _Work(
        card=LiveSourceCard(
            work_id=group[0].item.item_id,
            title=item.title[:320] if item.title else None,
            url=item.source_url,
            readable_url=readable.source_url if readable else None,
            first_round=group[0].item.round_number,
            state=state,
            note=note.strip()[:440] if note and note.strip() else None,
            note_kind=note_kind if note and note.strip() else None,
            angle=None,
        ),
        merit=merit,
        promising=promising,
        method=method,
        relationship=relationship,
    )


def _shortlist(works: list[_Work]) -> tuple[LiveSourceCard, ...]:
    ranked = sorted(
        (work for work in works if work.promising),
        key=lambda work: (-work.merit, work.card.first_round, str(work.card.work_id)),
    )
    strongest, remaining = ranked[:4], ranked[4:]
    methods = {work.method for work in strongest}
    relationships = {work.relationship for work in strongest}
    angles = []
    selected = {work.card.work_id for work in strongest}
    for work in remaining:
        angle = None
        if (
            work.relationship in {"challenges", "qualifies"}
            and work.relationship not in relationships
        ):
            angle = (
                "Challenges the claim"
                if work.relationship == "challenges"
                else "Qualifies the claim"
            )
        elif work.method and work.method not in methods:
            angle = work.method
        if angle is None:
            continue
        angles.append(work.card.model_copy(update={"angle": angle}))
        selected.add(work.card.work_id)
        methods.add(work.method)
        relationships.add(work.relationship)
        if len(angles) == 2:
            break
    latest_round = max((work.card.first_round for work in ranked), default=1)
    newcomer = next(
        (
            work.card.model_copy(update={"angle": f"New in round {latest_round}"})
            for work in remaining
            if latest_round > 1
            and work.card.first_round == latest_round
            and work.card.work_id not in selected
        ),
        None,
    )
    return (*[work.card for work in strongest], *angles, *((newcomer,) if newcomer else ()))


def read_live_sources(
    db_path: str | Path, run_id: UUID, *, known: str | None = None, offset: int | None = None
) -> LiveSourcesPage:
    with open_read_only_store(db_path) as store:
        with read_snapshot_connection(store.connection):
            read_run(store.connection, run_id)
            revision, values = _load(store.connection, run_id, known if offset is None else None)
            if values is None:
                return LiveSourcesPage(
                    run_id=run_id, revision=revision, unchanged=True, items=(), total=0
                )
            admitted = _admissions(store.connection, values)
    analysis = {
        value.source_id: value
        for value in values.values()
        if isinstance(value, V2EvidenceAnalystSourceResult) and value.assessment is not None
    }
    captures, full_text = _captures(values)
    works = [
        _work(group, captures, full_text, analysis, admitted)
        for group in _group_leads(values, captures)
    ]
    items = (
        _shortlist(works)
        if offset is None
        else tuple(work.card for work in works[offset : offset + 25])
    )
    return LiveSourcesPage(run_id=run_id, revision=revision, items=items, total=len(works))
