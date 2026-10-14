"""Strict, offline-only observation contracts; never production run permissions."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

Origin = Literal["fixture", "replayed_observation", "authorized_live"]
SHA = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
USD = Annotated[Decimal, Field(ge=0, allow_inf_nan=False)]
Stage = Literal[
    "returned",
    "normalized",
    "retained",
    "ranked",
    "scout",
    "acquisition",
    "capture",
    "selection",
    "extraction",
    "analyst",
    "admission",
    "visible",
]
STAGES = (
    "returned",
    "normalized",
    "retained",
    "ranked",
    "scout",
    "acquisition",
    "capture",
    "selection",
    "extraction",
    "analyst",
    "admission",
    "visible",
)


class Record(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Artifact(Record):
    path: str = Field(min_length=1)
    sha256: SHA
    media_type: str
    role: Literal["raw_response", "snapshot", "stage", "request", "judgment", "reference"]

    @model_validator(mode="after")
    def relative_path(self) -> Artifact:
        path = Path(self.path)
        if path.is_absolute() or ".." in path.parts:
            raise ValueError("artifact paths must stay inside the observation bundle")
        return self


class Judgment(Record):
    reviewer: str = Field(min_length=1)
    kind: Literal["human", "authored_fixture", "assistant"]
    rationale: str = Field(min_length=1)
    evidence_paths: tuple[str, ...] = Field(min_length=1)
    useful: bool | None = None
    relevant: bool | None = None
    capture: Literal["full_text", "abstract_only", "partial", "shell", "blocked", "unknown"]
    study_id: str | None = None
    independence_rationale: str | None = None

    @model_validator(mode="after")
    def study_basis(self) -> Judgment:
        if self.study_id is not None and not self.independence_rationale:
            raise ValueError("study grouping requires an explicit rationale")
        return self


class Reference(Record):
    work_id: str
    urls: tuple[str, ...] = Field(min_length=1)
    rationale: str = Field(min_length=1)


class ReferenceSet(Record):
    status: Literal["pending", "locked"]
    scope: Literal["non_exhaustive", "exhaustive_fixture"] = "non_exhaustive"
    method: str = Field(min_length=1)
    locked_at: datetime | None = None
    reviewer: str | None = None
    evidence: Artifact | None = None
    supporting_evidence: tuple[Artifact, ...] = ()
    works: tuple[Reference, ...] = ()

    @model_validator(mode="after")
    def lock_basis(self) -> ReferenceSet:
        if self.locked_at is not None and self.locked_at.utcoffset() is None:
            raise ValueError("reference lock time must include timezone")
        if len({w.work_id for w in self.works}) != len(self.works):
            raise ValueError("reference works must be unique")
        if self.status == "locked" and (
            not self.works or not self.reviewer or not self.locked_at or not self.evidence
        ):
            raise ValueError("locked useful reference set requires review, time and evidence")
        if (
            self.status == "locked"
            and self.evidence
            and (
                self.evidence.role != "reference" or self.evidence.media_type != "application/json"
            )
        ):
            raise ValueError(
                "locked reference evidence must be a canonical JSON reference artifact"
            )
        return self


class FrozenReference(Record):
    """Hash-bound scoring denominator and lock metadata; human evidence is separate."""

    schema_version: Literal["research-quality-reference-v1"] = "research-quality-reference-v1"
    topic_id: str
    claim_sha256: SHA
    scope: Literal["non_exhaustive", "exhaustive_fixture"]
    method: str = Field(min_length=1)
    locked_at: datetime
    reviewer: str = Field(min_length=1)
    works: tuple[Reference, ...] = Field(min_length=1)
    supporting_evidence: tuple[Artifact, ...] = ()

    @model_validator(mode="after")
    def lock_identity(self) -> FrozenReference:
        if self.locked_at.utcoffset() is None:
            raise ValueError("frozen reference lock must include timezone")
        if len({work.work_id for work in self.works}) != len(self.works):
            raise ValueError("frozen reference works must be unique")
        return self


class Topic(Record):
    topic_id: str
    split: Literal["development", "held_out"]
    claim: str
    rationale: str
    short_query: str
    concepts: tuple[str, ...]
    reference: ReferenceSet


class Disposition(Record):
    stage: Stage
    outcome: Literal["kept", "dropped", "failed", "not_reached", "not_observed"]
    reason: str = Field(min_length=1)
    evidence_path: str | None = None


class Candidate(Record):
    candidate_id: str
    attempt_id: str
    url: str
    work_id: str = Field(min_length=1)
    rank: int = Field(ge=1)
    snapshot_path: str | None = None
    judgment: Judgment | None = None
    dispositions: tuple[Disposition, ...]

    @model_validator(mode="after")
    def ordered_stages(self) -> Candidate:
        stages = [STAGES.index(d.stage) for d in self.dispositions]
        if stages != sorted(set(stages)) or not stages or stages[0] != 0:
            raise ValueError("candidate stages must be unique, ordered, and begin at returned")
        if self.dispositions[0].outcome != "kept":
            raise ValueError("candidate records represent provider-returned hits")
        terminal = False
        for disposition in self.dispositions:
            if terminal and disposition.outcome == "kept":
                raise ValueError("a dropped/failed candidate cannot survive a later stage")
            terminal |= disposition.outcome in {"dropped", "failed", "not_reached"}
        return self


class Attempt(Record):
    attempt_id: str
    category: Literal["search", "model", "acquisition"]
    provider: str
    endpoint: str
    settings: dict[str, str | int | bool | None]
    started_at: datetime
    finished_at: datetime | None = None
    outcome: Literal["success", "failure", "unknown"]
    request: Artifact
    request_kind: Literal["wire_request", "reservation_receipt"] = "wire_request"
    response: Artifact | None = None
    response_kind: Literal["wire_response", "completion_receipt"] = "wire_response"
    model_input: Artifact | None = None
    reserved_usd: USD
    actual_usd: USD | None = None
    cost_basis: str | None = None
    tokens: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def audit(self) -> Attempt:
        for value in (self.started_at, self.finished_at):
            if value is not None and value.utcoffset() is None:
                raise ValueError("physical attempt timestamps must include timezone")
        if self.finished_at is not None and self.finished_at < self.started_at:
            raise ValueError("attempt completion predates start")
        if self.outcome == "unknown" and self.actual_usd is not None:
            raise ValueError("unknown attempts retain reservation without guessed actual cost")
        if self.actual_usd is not None and not self.cost_basis:
            raise ValueError("actual cost requires an explicit basis")
        if self.outcome == "success" and (not self.response or not self.finished_at):
            raise ValueError("successful attempt requires a frozen response and completion")
        return self


class Statement(Record):
    statement_id: str
    text: str
    source_ids: tuple[str, ...]
    quote: str | None = None
    snapshot_path: str | None = None
    entailment: Literal["supported", "unsupported", "mixed", "unknown"]
    reviewer: str | None = None
    reviewer_kind: Literal["human", "authored_fixture", "assistant"] | None = None
    rationale: str | None = None


class Observation(Record):
    observation_id: str
    topic_id: str
    arm: str
    origin: Origin
    collector: str
    provenance_note: str = Field(min_length=1)
    allowance_id: str | None = None
    source_identity: str
    settings_sha256: SHA
    settings_path: str
    input_sha256: SHA
    started_at: datetime
    completed_at: datetime | None = None
    audit_complete: bool
    candidate_inventory_complete: bool
    final_inventory_complete: bool
    attempts: tuple[Attempt, ...] = ()
    artifacts: tuple[Artifact, ...] = ()
    discovery_handoff_paths: tuple[str, ...] = ()
    discovery_handoff_attempts: dict[str, tuple[str, ...]] = Field(default_factory=dict)
    search_attempt_result_paths: dict[str, str] = Field(default_factory=dict)
    candidates: tuple[Candidate, ...] = ()
    statements: tuple[Statement, ...] = ()

    @model_validator(mode="after")
    def closed_observation(self) -> Observation:
        if self.started_at.utcoffset() is None:
            raise ValueError("observation start must include timezone")
        if self.completed_at is not None and (
            self.completed_at.utcoffset() is None or self.completed_at < self.started_at
        ):
            raise ValueError("observation completion must be aware and follow start")
        if self.origin == "authorized_live" and not self.allowance_id:
            raise ValueError("live observation requires new explicit allowance provenance")
        attempts = {a.attempt_id: a for a in self.attempts}
        paths = {a.path for a in self.artifacts}
        if len(attempts) != len(self.attempts) or len(paths) != len(self.artifacts):
            raise ValueError("physical attempts and artifact paths must be unique")
        if not set(self.discovery_handoff_paths) <= paths:
            raise ValueError("discovery handoffs must be registered artifacts")
        if len(set(self.discovery_handoff_paths)) != len(self.discovery_handoff_paths):
            raise ValueError("discovery handoff paths must be unique")
        if not set(self.discovery_handoff_attempts) <= set(self.discovery_handoff_paths):
            raise ValueError("handoff attempt bindings require a registered handoff")
        bound_attempts = [
            attempt_id
            for identifiers in self.discovery_handoff_attempts.values()
            for attempt_id in identifiers
        ]
        if any(not identifiers for identifiers in self.discovery_handoff_attempts.values()):
            raise ValueError("each handoff binding requires successful physical attempts")
        if len(set(bound_attempts)) != len(bound_attempts):
            raise ValueError("each search attempt may belong to only one logical response handoff")
        for attempt_id in bound_attempts:
            if attempt_id not in attempts or attempts[attempt_id].category != "search":
                raise ValueError("discovery handoff requires an owned search attempt")
        for attempt_id, result_path in self.search_attempt_result_paths.items():
            if (
                attempt_id not in attempts
                or attempts[attempt_id].category != "search"
                or result_path not in paths
            ):
                raise ValueError(
                    "physical page projection requires an owned search attempt/artifact"
                )
        if self.candidate_inventory_complete and set(self.discovery_handoff_attempts) != set(
            self.discovery_handoff_paths
        ):
            raise ValueError("complete discovery replay requires query/attempt bindings")
        if self.settings_path not in paths:
            raise ValueError("exact run settings require an owned artifact")
        if (
            next(a for a in self.artifacts if a.path == self.settings_path).sha256
            != self.settings_sha256
        ):
            raise ValueError("settings digest must bind the exact settings artifact")
        ids = {c.candidate_id for c in self.candidates}
        if len(ids) != len(self.candidates):
            raise ValueError("candidate IDs must be unique")
        if len({s.statement_id for s in self.statements}) != len(self.statements):
            raise ValueError("final statement IDs must be unique")
        for attempt in self.attempts:
            for artifact in (attempt.request, attempt.response, attempt.model_input):
                if artifact and artifact not in self.artifacts:
                    raise ValueError("attempt files must be registered exactly")
        for candidate in self.candidates:
            if candidate.attempt_id not in attempts:
                raise ValueError("candidate requires an owned physical attempt")
            if attempts[candidate.attempt_id].category != "search":
                raise ValueError("candidate must originate in search")
            if self.origin != "fixture" and ".invalid" in candidate.url:
                raise ValueError("fixture URLs cannot become real observations")
            required = [d.evidence_path for d in candidate.dispositions if d.evidence_path]
            if candidate.snapshot_path:
                required.append(candidate.snapshot_path)
                if not any(
                    a.path == candidate.snapshot_path and a.role == "snapshot"
                    for a in self.artifacts
                ):
                    raise ValueError("capture requires a registered snapshot artifact")
            if candidate.judgment:
                required.extend(candidate.judgment.evidence_paths)
                if self.origin != "fixture" and candidate.judgment.kind == "authored_fixture":
                    raise ValueError("authored judgments cannot grade real observations")
            if not set(required) <= paths:
                raise ValueError("candidate evidence must be owned frozen artifacts")
        for statement in self.statements:
            if not set(statement.source_ids) <= ids:
                raise ValueError("statement sources must belong to the observation")
            if statement.snapshot_path and statement.snapshot_path not in paths:
                raise ValueError("statement snapshot must be owned")
            if statement.entailment != "unknown" and (
                not statement.reviewer or not statement.rationale or not statement.reviewer_kind
            ):
                raise ValueError("entailment requires a review rationale")
            if statement.entailment == "supported" and (
                not statement.source_ids or not statement.quote or not statement.snapshot_path
            ):
                raise ValueError("supported statements require source and exact snapshot quote")
            if self.origin != "fixture" and statement.reviewer_kind == "authored_fixture":
                raise ValueError("authored entailment cannot grade real observations")
        return self


class Benchmark(Record):
    schema_version: Literal["research-quality-v1"]
    prepared_on: str
    baseline: dict[str, object]
    topics: tuple[Topic, ...]
    observations: tuple[Observation, ...] = ()

    @model_validator(mode="after")
    def topic_ownership(self) -> Benchmark:
        topics = {t.topic_id: t for t in self.topics}
        if len(topics) != len(self.topics):
            raise ValueError("topics must be unique")
        if len({o.observation_id for o in self.observations}) != len(self.observations):
            raise ValueError("observations must be unique")
        for observation in self.observations:
            if observation.topic_id not in topics:
                raise ValueError("observation topic is absent")
            ref = topics[observation.topic_id].reference
            if ref.status == "locked" and ref.locked_at and ref.locked_at > observation.started_at:
                raise ValueError("reference must be locked before observing comparison output")
            if observation.origin != "fixture" and ref.scope == "exhaustive_fixture":
                raise ValueError("fixture reference set cannot establish live recall")
        return self
