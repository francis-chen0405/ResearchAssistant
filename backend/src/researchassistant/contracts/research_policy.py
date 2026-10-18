"""Research policy identities and canonical persistence envelopes."""

from __future__ import annotations

import json
from datetime import datetime
from hashlib import sha256
from typing import Annotated, Literal
from uuid import UUID

from pydantic import (
    ConfigDict,
    Field,
    field_validator,
)

from researchassistant.contracts.model_contracts import (
    NonEmptyStr,
    StrictModel,
    _validate_aware_datetime,
)

V2_PIPELINE_IDENTITY = "researchassistant-v2"


V2_POLICY_IDENTITY = "researchassistant-v2-phase-1"


V2_INITIAL_PLANNER_POLICY_IDENTITY = "researchassistant-v2-phase-3-initial-planner-v1"


V2_DISCOVERY_POLICY_IDENTITY = "researchassistant-v2-phase-4-discovery-scout-v1"


V2_ACQUISITION_PROBE_LEGACY_POLICY_IDENTITY = "researchassistant-v2-phase-5-acquisition-probe-v1"


V2_ACQUISITION_PROBE_POLICY_IDENTITY = "researchassistant-v2-phase-5-acquisition-probe-v2"


V2_CLAIM_PREVIEW_PROBE_POLICY_IDENTITY = "researchassistant-v2-phase-5-acquisition-probe-v3"


V2_USABLE_CAPTURE_PROBE_POLICY_IDENTITY = "researchassistant-v2-phase-5-acquisition-probe-v4"


V2_PREVIEW_SELECTION_LEGACY_POLICY_IDENTITY = "researchassistant-v2-phase-8-source-selection-v2"
V2_PREVIEW_SELECTION_POLICY_IDENTITY = "researchassistant-v2-phase-8-source-selection-v3"
V2_CLAIM_PREVIEW_SELECTION_POLICIES = frozenset(
    {
        V2_PREVIEW_SELECTION_LEGACY_POLICY_IDENTITY,
        V2_PREVIEW_SELECTION_POLICY_IDENTITY,
    }
)
V2_FOUR_ROUND_SURVIVOR_LIMIT = 100


V2_GAP_ANALYSIS_POLICY_IDENTITY = "researchassistant-v2-phase-6-gap-analysis-v1"


V2_ADAPTIVE_SEARCH_POLICY_IDENTITY = "researchassistant-v2-phase-7-adaptive-search-v1"


V2_POST13_ROUND_FOUR_POLICY_IDENTITY = "researchassistant-v2-post-phase-13-round-four-v1"


V2_POST13_GAP_ANALYSIS_POLICY_IDENTITY = "researchassistant-v2-post-phase-13-gap-analysis-v1"


V2_SOURCE_SELECTION_POLICY_IDENTITY = "researchassistant-v2-phase-8-source-selection-v1"


V2_DEEP_ANALYSIS_QUEUE_POLICY_IDENTITY = (
    "researchassistant-v2-phase-13-deep-analysis-queue-analyzer-admission-v1"
)


V2_EVIDENCE_ANALYST_LEGACY_POLICY_IDENTITY = (
    "researchassistant-v2-phase-13-luna-evidence-analyst-analyzer-admission-v1"
)


V2_EVIDENCE_ANALYST_PREVIOUS_POLICY_IDENTITY = (
    "researchassistant-v2-phase-13-luna-evidence-analyst-analyzer-admission-v2"
)


V2_EVIDENCE_ANALYST_POLICY_IDENTITY = (
    "researchassistant-v2-phase-13-luna-evidence-analyst-analyzer-admission-v3"
)


V2_EVIDENCE_ADMISSION_LEGACY_POLICY_IDENTITY = "researchassistant-v2-phase-13-analyzer-admission-v1"


V2_EVIDENCE_ADMISSION_PREVIOUS_POLICY_IDENTITY = (
    "researchassistant-v2-phase-13-analyzer-admission-v2"
)


V2_EVIDENCE_ADMISSION_POLICY_IDENTITY = "researchassistant-v2-phase-13-analyzer-admission-v3"


V2_REVIEWER_LEDGER_POLICY_IDENTITY = "researchassistant-v2-phase-10-reviewer-ledger-v2"


V2_DEEP_ANALYSIS_BACKFILL_POLICY_IDENTITY = (
    "researchassistant-v2-phase-13-deep-analysis-backfill-analyzer-admission-v2-waves4"
)


V2_DEEP_ANALYSIS_SOURCE_TOKEN_CAP = 60_000


V2_DEEP_ANALYSIS_SOURCE_PHYSICAL_CALL_CAP = 3


class V2PipelineIdentity(StrictModel):
    """Version and policy identity persisted before a v2 artifact is admitted."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    pipeline_identity: Literal["researchassistant-v2"] = V2_PIPELINE_IDENTITY
    policy_identity: Literal["researchassistant-v2-phase-1"] = V2_POLICY_IDENTITY

    def canonical_json(self) -> str:
        return json.dumps(self.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))


def canonical_v2_artifact_json(artifact: StrictModel) -> str:
    """Return canonical bytes for a strict v2 artifact at a persistence boundary."""
    return json.dumps(artifact.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))


def v2_payload_fingerprint(payload_json: str) -> str:
    """Return the SHA-256 identity of canonical v2 payload JSON bytes."""
    return sha256(payload_json.encode("utf-8")).hexdigest()


def v2_artifact_fingerprint(artifact: StrictModel) -> str:
    """Return the SHA-256 identity of a canonical v2 artifact."""
    return v2_payload_fingerprint(canonical_v2_artifact_json(artifact))


class V2PersistedArtifact(StrictModel):
    """Canonical persistence envelope for a typed v2 artifact."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: UUID
    artifact_key: NonEmptyStr
    artifact_type: NonEmptyStr
    payload_json: NonEmptyStr
    payload_sha256: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
    created_at: datetime

    _created_at_is_aware = field_validator("created_at")(_validate_aware_datetime)


# Preserve the historical public class identity for persisted consumers.
V2PipelineIdentity.__module__ = "researchassistant.contracts.model_research"
V2PersistedArtifact.__module__ = "researchassistant.contracts.model_research"
