"""Compatible public re-exports of research contracts by stage."""

from __future__ import annotations

import json as json
from datetime import datetime as datetime
from decimal import Decimal as Decimal
from enum import StrEnum as StrEnum
from hashlib import sha256 as sha256
from typing import Annotated as Annotated
from typing import Literal as Literal
from uuid import UUID as UUID

from pydantic import ConfigDict as ConfigDict
from pydantic import Field as Field
from pydantic import SerializerFunctionWrapHandler as SerializerFunctionWrapHandler
from pydantic import field_validator as field_validator
from pydantic import model_serializer as model_serializer
from pydantic import model_validator as model_validator
from pydantic_core import PydanticCustomError as PydanticCustomError

from researchassistant.common.money import ExactUSD as ExactUSD
from researchassistant.contracts.discovery_v2 import V2CompiledQueryAction as V2CompiledQueryAction
from researchassistant.contracts.discovery_v2 import V2GraphNeighborAction as V2GraphNeighborAction
from researchassistant.contracts.discovery_v2 import V2PreviewResult as V2PreviewResult
from researchassistant.contracts.metadata_ranking import MetadataRank as MetadataRank
from researchassistant.contracts.model_contracts import DiscoveryProvider as DiscoveryProvider
from researchassistant.contracts.model_contracts import NonEmptyStr as NonEmptyStr
from researchassistant.contracts.model_contracts import NonNegativeInt as NonNegativeInt
from researchassistant.contracts.model_contracts import PositiveInt as PositiveInt
from researchassistant.contracts.model_contracts import SourceSnapshot as SourceSnapshot
from researchassistant.contracts.model_contracts import StrictModel as StrictModel
from researchassistant.contracts.model_contracts import (
    _validate_aware_datetime as _validate_aware_datetime,
)
from researchassistant.contracts.research_acquisition import (
    V2AcquiredSource as V2AcquiredSource,
)
from researchassistant.contracts.research_acquisition import (
    V2AcquisitionAttempt as V2AcquisitionAttempt,
)
from researchassistant.contracts.research_acquisition import (
    V2AcquisitionPolicy as V2AcquisitionPolicy,
)
from researchassistant.contracts.research_acquisition import (
    V2AcquisitionProbeOutput as V2AcquisitionProbeOutput,
)
from researchassistant.contracts.research_acquisition import (
    V2AcquisitionProvider as V2AcquisitionProvider,
)
from researchassistant.contracts.research_acquisition import (
    V2ProbePassage as V2ProbePassage,
)
from researchassistant.contracts.research_acquisition import (
    V2ProbeResult as V2ProbeResult,
)
from researchassistant.contracts.research_acquisition import (
    V2SurvivingSource as V2SurvivingSource,
)
from researchassistant.contracts.research_coverage import (
    V2ClaimCoverageAssessment as V2ClaimCoverageAssessment,
)
from researchassistant.contracts.research_coverage import (
    V2ClaimCoverageDimension as V2ClaimCoverageDimension,
)
from researchassistant.contracts.research_coverage import (
    V2ClaimCoverageFocus as V2ClaimCoverageFocus,
)
from researchassistant.contracts.research_coverage import (
    V2ClaimCoverageKind as V2ClaimCoverageKind,
)
from researchassistant.contracts.research_coverage import (
    V2ClaimCoverageSpecification as V2ClaimCoverageSpecification,
)
from researchassistant.contracts.research_coverage import (
    V2ClaimCoverageState as V2ClaimCoverageState,
)
from researchassistant.contracts.research_coverage import (
    V2GapIdentity as V2GapIdentity,
)
from researchassistant.contracts.research_coverage import (
    V2GapIdentityCollisionError as V2GapIdentityCollisionError,
)
from researchassistant.contracts.research_coverage import (
    V2InitialPlannerClaimComponent as V2InitialPlannerClaimComponent,
)
from researchassistant.contracts.research_coverage import (
    V2MaterialGap as V2MaterialGap,
)
from researchassistant.contracts.research_coverage import (
    V2SourceSelectionGap as V2SourceSelectionGap,
)
from researchassistant.contracts.research_coverage import (
    _record_v2_gap_identity as _record_v2_gap_identity,
)
from researchassistant.contracts.research_coverage import (
    validate_v2_gap_history_against_material_gaps as validate_v2_gap_history_against_material_gaps,
)
from researchassistant.contracts.research_coverage import (
    validate_v2_gap_identity_continuity as validate_v2_gap_identity_continuity,
)
from researchassistant.contracts.research_coverage import (
    validate_v2_source_selection_gap_history as validate_v2_source_selection_gap_history,
)
from researchassistant.contracts.research_directions import ResearchDirection as ResearchDirection
from researchassistant.contracts.research_directions import ResearchDirections as ResearchDirections
from researchassistant.contracts.research_discovery import (
    CrossrefIdentityMetadata as CrossrefIdentityMetadata,
)
from researchassistant.contracts.research_discovery import (
    DiscoveryMetadataEntry as DiscoveryMetadataEntry,
)
from researchassistant.contracts.research_discovery import (
    DiscoveryProvenance as DiscoveryProvenance,
)
from researchassistant.contracts.research_discovery import (
    DiscoveryProviderReference as DiscoveryProviderReference,
)
from researchassistant.contracts.research_discovery import (
    NormalizedDiscoveryItem as NormalizedDiscoveryItem,
)
from researchassistant.contracts.research_discovery import (
    ScoutBatch as ScoutBatch,
)
from researchassistant.contracts.research_discovery import (
    ScoutBatchAudit as ScoutBatchAudit,
)
from researchassistant.contracts.research_discovery import (
    ScoutCandidate as ScoutCandidate,
)
from researchassistant.contracts.research_discovery import (
    ScoutDecision as ScoutDecision,
)
from researchassistant.contracts.research_discovery import (
    ScoutItem as ScoutItem,
)
from researchassistant.contracts.research_discovery import (
    SourceCluster as SourceCluster,
)
from researchassistant.contracts.research_discovery import (
    V2DiscoveryScoutOutput as V2DiscoveryScoutOutput,
)
from researchassistant.contracts.research_discovery import (
    V2ScoutRequest as V2ScoutRequest,
)
from researchassistant.contracts.research_gaps import (
    V2GapAcquisitionFailure as V2GapAcquisitionFailure,
)
from researchassistant.contracts.research_gaps import (
    V2GapAnalysisAttempt as V2GapAnalysisAttempt,
)
from researchassistant.contracts.research_gaps import (
    V2GapAnalysisInput as V2GapAnalysisInput,
)
from researchassistant.contracts.research_gaps import (
    V2GapAnalysisModelOutput as V2GapAnalysisModelOutput,
)
from researchassistant.contracts.research_gaps import (
    V2GapAnalysisOutput as V2GapAnalysisOutput,
)
from researchassistant.contracts.research_gaps import (
    V2GapAnalysisResult as V2GapAnalysisResult,
)
from researchassistant.contracts.research_gaps import (
    V2GapAnalysisState as V2GapAnalysisState,
)
from researchassistant.contracts.research_gaps import (
    V2GapAttemptedQuery as V2GapAttemptedQuery,
)
from researchassistant.contracts.research_gaps import (
    V2GapBudgetState as V2GapBudgetState,
)
from researchassistant.contracts.research_gaps import (
    V2GapDuplicatePattern as V2GapDuplicatePattern,
)
from researchassistant.contracts.research_gaps import (
    V2GapProbePassage as V2GapProbePassage,
)
from researchassistant.contracts.research_gaps import (
    V2GapReservation as V2GapReservation,
)
from researchassistant.contracts.research_gaps import (
    V2GapSearchDirection as V2GapSearchDirection,
)
from researchassistant.contracts.research_gaps import (
    V2GapSourceFamily as V2GapSourceFamily,
)
from researchassistant.contracts.research_gaps import (
    V2GapSurvivingSourceMetadata as V2GapSurvivingSourceMetadata,
)
from researchassistant.contracts.research_historical import (
    DeepAnalysisState as DeepAnalysisState,
)
from researchassistant.contracts.research_historical import (
    DeepAnalysisStatus as DeepAnalysisStatus,
)
from researchassistant.contracts.research_historical import (
    GapAnalysisResult as GapAnalysisResult,
)
from researchassistant.contracts.research_historical import (
    ProbePassage as ProbePassage,
)
from researchassistant.contracts.research_historical import (
    ProbeResult as ProbeResult,
)
from researchassistant.contracts.research_historical import (
    SourceRecommendationResult as SourceRecommendationResult,
)
from researchassistant.contracts.research_historical import (
    SurvivingSourceRecord as SurvivingSourceRecord,
)
from researchassistant.contracts.research_planning import (
    SearchDirectionGapReference as SearchDirectionGapReference,
)
from researchassistant.contracts.research_planning import (
    V2AdaptiveRoundPlan as V2AdaptiveRoundPlan,
)
from researchassistant.contracts.research_planning import (
    V2AdaptiveSearchModelOutput as V2AdaptiveSearchModelOutput,
)
from researchassistant.contracts.research_planning import (
    V2AdaptiveSearchProposal as V2AdaptiveSearchProposal,
)
from researchassistant.contracts.research_planning import (
    V2AdaptiveSearchQuery as V2AdaptiveSearchQuery,
)
from researchassistant.contracts.research_planning import (
    V2InitialPlannerInput as V2InitialPlannerInput,
)
from researchassistant.contracts.research_planning import (
    V2InitialPlannerModelOutput as V2InitialPlannerModelOutput,
)
from researchassistant.contracts.research_planning import (
    V2InitialPlannerOutput as V2InitialPlannerOutput,
)
from researchassistant.contracts.research_planning import (
    V2InitialPlannerPolicy as V2InitialPlannerPolicy,
)
from researchassistant.contracts.research_planning import (
    V2InitialPlannerSearchLane as V2InitialPlannerSearchLane,
)
from researchassistant.contracts.research_planning import (
    V2InitialPlannerSearchResponse as V2InitialPlannerSearchResponse,
)
from researchassistant.contracts.research_planning import (
    V2InitialResearchPlan as V2InitialResearchPlan,
)
from researchassistant.contracts.research_planning import (
    V2PlannedSearch as V2PlannedSearch,
)
from researchassistant.contracts.research_planning import (
    V2ProviderSearchBudget as V2ProviderSearchBudget,
)
from researchassistant.contracts.research_planning import (
    V2RoundOneSearchQuery as V2RoundOneSearchQuery,
)
from researchassistant.contracts.research_planning import (
    V2ScopeInterpretation as V2ScopeInterpretation,
)
from researchassistant.contracts.research_planning import (
    V2SearchAgentInput as V2SearchAgentInput,
)
from researchassistant.contracts.research_planning import (
    V2SearchRoundPlan as V2SearchRoundPlan,
)
from researchassistant.contracts.research_planning import (
    _validate_v2_discovery_providers as _validate_v2_discovery_providers,
)
from researchassistant.contracts.research_policy import (
    V2_ACQUISITION_PROBE_LEGACY_POLICY_IDENTITY as V2_ACQUISITION_PROBE_LEGACY_POLICY_IDENTITY,
)
from researchassistant.contracts.research_policy import (
    V2_ACQUISITION_PROBE_POLICY_IDENTITY as V2_ACQUISITION_PROBE_POLICY_IDENTITY,
)
from researchassistant.contracts.research_policy import (
    V2_ADAPTIVE_SEARCH_POLICY_IDENTITY as V2_ADAPTIVE_SEARCH_POLICY_IDENTITY,
)
from researchassistant.contracts.research_policy import (
    V2_CLAIM_PREVIEW_PROBE_POLICY_IDENTITY as V2_CLAIM_PREVIEW_PROBE_POLICY_IDENTITY,
)
from researchassistant.contracts.research_policy import (
    V2_DEEP_ANALYSIS_BACKFILL_POLICY_IDENTITY as V2_DEEP_ANALYSIS_BACKFILL_POLICY_IDENTITY,
)
from researchassistant.contracts.research_policy import (
    V2_DEEP_ANALYSIS_QUEUE_POLICY_IDENTITY as V2_DEEP_ANALYSIS_QUEUE_POLICY_IDENTITY,
)
from researchassistant.contracts.research_policy import (
    V2_DEEP_ANALYSIS_SOURCE_PHYSICAL_CALL_CAP as V2_DEEP_ANALYSIS_SOURCE_PHYSICAL_CALL_CAP,
)
from researchassistant.contracts.research_policy import (
    V2_DEEP_ANALYSIS_SOURCE_TOKEN_CAP as V2_DEEP_ANALYSIS_SOURCE_TOKEN_CAP,
)
from researchassistant.contracts.research_policy import (
    V2_DISCOVERY_POLICY_IDENTITY as V2_DISCOVERY_POLICY_IDENTITY,
)
from researchassistant.contracts.research_policy import (
    V2_EVIDENCE_ADMISSION_LEGACY_POLICY_IDENTITY as V2_EVIDENCE_ADMISSION_LEGACY_POLICY_IDENTITY,
)
from researchassistant.contracts.research_policy import (
    V2_EVIDENCE_ADMISSION_POLICY_IDENTITY as V2_EVIDENCE_ADMISSION_POLICY_IDENTITY,
)
from researchassistant.contracts.research_policy import (
    V2_EVIDENCE_ADMISSION_PREVIOUS_POLICY_IDENTITY,  # noqa: F401 - compatibility export
)
from researchassistant.contracts.research_policy import (
    V2_EVIDENCE_ANALYST_LEGACY_POLICY_IDENTITY as V2_EVIDENCE_ANALYST_LEGACY_POLICY_IDENTITY,
)
from researchassistant.contracts.research_policy import (
    V2_EVIDENCE_ANALYST_POLICY_IDENTITY as V2_EVIDENCE_ANALYST_POLICY_IDENTITY,
)
from researchassistant.contracts.research_policy import (
    V2_EVIDENCE_ANALYST_PREVIOUS_POLICY_IDENTITY as V2_EVIDENCE_ANALYST_PREVIOUS_POLICY_IDENTITY,
)
from researchassistant.contracts.research_policy import (
    V2_GAP_ANALYSIS_POLICY_IDENTITY as V2_GAP_ANALYSIS_POLICY_IDENTITY,
)
from researchassistant.contracts.research_policy import (
    V2_INITIAL_PLANNER_POLICY_IDENTITY as V2_INITIAL_PLANNER_POLICY_IDENTITY,
)
from researchassistant.contracts.research_policy import (
    V2_PIPELINE_IDENTITY as V2_PIPELINE_IDENTITY,
)
from researchassistant.contracts.research_policy import (
    V2_POLICY_IDENTITY as V2_POLICY_IDENTITY,
)
from researchassistant.contracts.research_policy import (
    V2_POST13_GAP_ANALYSIS_POLICY_IDENTITY as V2_POST13_GAP_ANALYSIS_POLICY_IDENTITY,
)
from researchassistant.contracts.research_policy import (
    V2_POST13_ROUND_FOUR_POLICY_IDENTITY as V2_POST13_ROUND_FOUR_POLICY_IDENTITY,
)
from researchassistant.contracts.research_policy import (
    V2_PREVIEW_SELECTION_POLICY_IDENTITY as V2_PREVIEW_SELECTION_POLICY_IDENTITY,
)
from researchassistant.contracts.research_policy import (
    V2_REVIEWER_LEDGER_POLICY_IDENTITY as V2_REVIEWER_LEDGER_POLICY_IDENTITY,
)
from researchassistant.contracts.research_policy import (
    V2_SOURCE_SELECTION_POLICY_IDENTITY as V2_SOURCE_SELECTION_POLICY_IDENTITY,
)
from researchassistant.contracts.research_policy import (
    V2_USABLE_CAPTURE_PROBE_POLICY_IDENTITY as V2_USABLE_CAPTURE_PROBE_POLICY_IDENTITY,
)
from researchassistant.contracts.research_policy import (
    V2PersistedArtifact as V2PersistedArtifact,
)
from researchassistant.contracts.research_policy import (
    V2PipelineIdentity as V2PipelineIdentity,
)
from researchassistant.contracts.research_policy import (
    canonical_v2_artifact_json as canonical_v2_artifact_json,
)
from researchassistant.contracts.research_policy import (
    v2_artifact_fingerprint as v2_artifact_fingerprint,
)
from researchassistant.contracts.research_policy import (
    v2_payload_fingerprint as v2_payload_fingerprint,
)
from researchassistant.contracts.research_round_four import (
    V2GapCoverageReconciliation as V2GapCoverageReconciliation,
)
from researchassistant.contracts.research_round_four import (
    V2GapCoverageRecord as V2GapCoverageRecord,
)
from researchassistant.contracts.research_round_four import (
    V2GapCoverageState as V2GapCoverageState,
)
from researchassistant.contracts.research_round_four import (
    V2RoundFourDecisionCode as V2RoundFourDecisionCode,
)
from researchassistant.contracts.research_round_four import (
    V2RoundFourGovernorDecision as V2RoundFourGovernorDecision,
)
from researchassistant.contracts.research_round_four import (
    V2RoundFourReservation as V2RoundFourReservation,
)
from researchassistant.contracts.research_round_four import (
    V2RoundFourTerminalOutcome as V2RoundFourTerminalOutcome,
)
from researchassistant.contracts.research_selection import (
    V2DeepAnalysisBudget as V2DeepAnalysisBudget,
)
from researchassistant.contracts.research_selection import (
    V2DeepAnalysisBudgetReason as V2DeepAnalysisBudgetReason,
)
from researchassistant.contracts.research_selection import (
    V2DeepAnalysisQueuePlan as V2DeepAnalysisQueuePlan,
)
from researchassistant.contracts.research_selection import (
    V2DeepAnalysisSourceStatus as V2DeepAnalysisSourceStatus,
)
from researchassistant.contracts.research_selection import (
    V2DeepAnalysisTokenReservation as V2DeepAnalysisTokenReservation,
)
from researchassistant.contracts.research_selection import (
    V2SourceSelectionAttempt as V2SourceSelectionAttempt,
)
from researchassistant.contracts.research_selection import (
    V2SourceSelectionCandidate as V2SourceSelectionCandidate,
)
from researchassistant.contracts.research_selection import (
    V2SourceSelectionInput as V2SourceSelectionInput,
)
from researchassistant.contracts.research_selection import (
    V2SourceSelectionModelOutput as V2SourceSelectionModelOutput,
)
from researchassistant.contracts.research_selection import (
    V2SourceSelectionProbePassage as V2SourceSelectionProbePassage,
)
from researchassistant.contracts.research_selection import (
    V2SourceSelectionQueueResult as V2SourceSelectionQueueResult,
)
from researchassistant.contracts.research_selection import (
    V2SourceSelectionRecommendation as V2SourceSelectionRecommendation,
)
from researchassistant.contracts.research_selection import (
    V2SourceSelectionSearchProvenance as V2SourceSelectionSearchProvenance,
)
