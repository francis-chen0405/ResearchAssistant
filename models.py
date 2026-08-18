from __future__ import annotations

import json
from datetime import datetime
from enum import StrEnum
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from money import ExactUSD
from provider_contract import parse_provider_contract_payload, provider_contract_fingerprint

Score = Annotated[int, Field(ge=1, le=5)]
ApprovedScore = Annotated[int, Field(ge=3, le=5)]
PositiveInt = Annotated[int, Field(ge=1)]
NonNegativeInt = Annotated[int, Field(ge=0)]
NonEmptyStr = Annotated[str, Field(min_length=1)]
ApplicationReviewerApprovalId = Annotated[
    str,
    Field(pattern=r"^rappr_v1_[0-9a-f]{64}$"),
]
ReviewerApprovalId = UUID | ApplicationReviewerApprovalId
REQUIRED_QUERY_EXCLUSIONS = (
    "-site:reddit.com",
    "-site:quora.com",
    "-site:youtube.com",
    "-site:tiktok.com",
)


def missing_required_query_exclusions(exclusion_parameters: str) -> tuple[str, ...]:
    """Return required search exclusions absent as exact whitespace-delimited tokens."""
    tokens = set(exclusion_parameters.split())
    return tuple(exclusion for exclusion in REQUIRED_QUERY_EXCLUSIONS if exclusion not in tokens)


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ResearchDepth(StrEnum):
    FOCUSED = "focused"
    STANDARD = "standard"


class ResearchMode(StrEnum):
    FOCUSED = "focused"
    BALANCED = "balanced"


class DiscoveryProvider(StrEnum):
    EXA = "exa"
    OPENALEX = "openalex"


class SearchIntent(StrEnum):
    BROAD_WEB = "broad_web"
    ACADEMIC_STUDY = "academic_study"
    GOVERNMENT_INSTITUTIONAL = "government_institutional"
    NEWS_CURRENT = "news_current"
    LIMITATIONS_COUNTEREVIDENCE = "limitations_counterevidence"


class ReportLength(StrEnum):
    BRIEF = "brief"
    REPORT = "report"


class PresentationTone(StrEnum):
    NEUTRAL = "neutral"
    EXECUTIVE = "executive"
    ACADEMIC = "academic"
    PLAIN_LANGUAGE = "plain_language"


class ResearchFocus(StrictModel):
    """Explicit optional planner constraints; never inferred from the claim."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    geographic_area: NonEmptyStr | None = None
    timeframe: NonEmptyStr | None = None
    population: NonEmptyStr | None = None
    analytical_lens: NonEmptyStr | None = None

    @field_validator("geographic_area", "timeframe", "population", "analytical_lens")
    @classmethod
    def validate_trimmed(cls, value: str | None) -> str | None:
        if value is not None and value != value.strip():
            raise ValueError("focus values must not have leading or trailing whitespace")
        return value

    @model_validator(mode="after")
    def validate_present(self) -> ResearchFocus:
        if not any((self.geographic_area, self.timeframe, self.population, self.analytical_lens)):
            raise ValueError("focus must include at least one explicit constraint")
        return self


class ResearchControls(StrictModel):
    """Frozen operator choices whose canonical JSON is part of run compatibility."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    depth: ResearchDepth = ResearchDepth.STANDARD
    length: ReportLength = ReportLength.REPORT
    tone: PresentationTone = PresentationTone.NEUTRAL
    focus: ResearchFocus | None = None
    research_mode: ResearchMode = ResearchMode.FOCUSED
    sources_per_stance_per_round: Literal[5, 7, 10, 15, 20] = 10

    def canonical_json(self) -> str:
        return json.dumps(self.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))

    @classmethod
    def from_policy_identity(cls, policy_identity: str) -> ResearchControls:
        """Recover controls from an immutable policy identity with later policy segments."""
        marker = "|controls:"
        if marker not in policy_identity:
            return DEFAULT_RESEARCH_CONTROLS
        try:
            encoded = policy_identity.split(marker, 1)[1]
            payload, end = json.JSONDecoder().raw_decode(encoded)
            suffix = encoded[end:]
            if suffix and not suffix.startswith("|"):
                raise ValueError("controls JSON must end before a policy segment boundary")
            return cls.model_validate(payload)
        except (json.JSONDecodeError, ValueError) as exc:
            raise ValueError("provider contract has no valid persisted research controls") from exc


DEFAULT_RESEARCH_CONTROLS = ResearchControls()


class RunStatus(StrEnum):
    PLANNED = "planned"
    RUNNING = "running"
    COMPLETED = "completed"
    BLOCKED = "blocked"
    CANCELLED = "cancelled"
    FAILED = "failed"


class CheckpointStatus(StrEnum):
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    BLOCKED = "blocked"


class ModelAttemptStatus(StrEnum):
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class Stage(StrEnum):
    CLAIM_PLANNER = "claim_planner"
    SUPPORTING_RESEARCHER = "supporting_researcher"
    OPPOSING_RESEARCHER = "opposing_researcher"
    EVIDENCE_ANALYST = "evidence_analyst"
    STATEMENT_REVIEWER = "statement_reviewer"
    CLAIM_LEDGER = "claim_ledger"
    DEBATE_SYNTHESIZER = "debate_synthesizer"
    FINAL_RENDERER_VALIDATOR = "final_renderer_validator"


class Stance(StrEnum):
    SUPPORTING = "supporting"
    OPPOSING = "opposing"


class ResearchRound(StrEnum):
    INITIAL = "initial"
    TARGETED = "targeted"


class EvidenceRole(StrEnum):
    SUPPORTING = "supporting"
    OPPOSING = "opposing"
    LIMITATION = "limitation"


class EvidenceTrailOutcome(StrEnum):
    ACCEPTED = "accepted"
    DUPLICATE = "duplicate"
    INACCESSIBLE = "inaccessible"
    UNSUPPORTED_CONTENT = "unsupported_content"
    RETRIEVAL_FAILURE = "retrieval_failure"
    PASSAGE_SELECTION_FAILED = "passage_selection_failed"
    QUOTE_VALIDATION_FAILED = "quote_validation_failed"
    EVIDENCE_DENSITY_FAILURE = "evidence_density_failure"
    ANALYST_REJECTED = "analyst_rejected"
    REVIEWER_REJECTED = "reviewer_rejected"
    NOT_RELEVANT = "not_relevant"
    BUDGET_PREVENTED = "budget_prevented"


class CoverageRating(StrEnum):
    STRONG = "strong"
    ADEQUATE = "adequate"
    LIMITED = "limited"
    INSUFFICIENT = "insufficient"


class Placement(StrEnum):
    PRIMARY = "primary"
    SECONDARY = "secondary"
    SUPPORTING = "supporting"
    QUALIFIED_ONLY = "qualified_only"


class Entailment(StrEnum):
    STRONG = "Strong"
    PARTIAL = "Partial"
    WEAK = "Weak"


def entailment_for_claim_fit(claim_fit: int) -> Entailment:
    """Return the single application-owned entailment label for a Ledger-eligible fit."""
    try:
        return {
            3: Entailment.WEAK,
            4: Entailment.PARTIAL,
            5: Entailment.STRONG,
        }[claim_fit]
    except KeyError as exc:
        raise ValueError("Ledger Claim Fit must be 3, 4, or 5") from exc


class RetrievalStatus(StrEnum):
    RETRIEVED = "retrieved"
    FAILED = "failed"
    SKIPPED = "skipped"


class ReviewerFailureCode(StrEnum):
    NOT_ENTAILED = "not_entailed"
    MISSING_QUALIFICATION = "missing_qualification"
    BIASED_FRAMING = "biased_framing"
    CLAIM_FIT_MISMATCH = "claim_fit_mismatch"


class SectionType(StrEnum):
    SUPPORTING = "supporting"
    OPPOSING = "opposing"
    LIMITATIONS = "limitations"


BRIEF_TITLE = "Research Brief"
CLAIM_LABEL = "Claim under review"
RELEASE_SECTION_ORDER = (
    SectionType.SUPPORTING,
    SectionType.OPPOSING,
    SectionType.LIMITATIONS,
)
RELEASE_SECTION_HEADINGS = {
    SectionType.SUPPORTING: "Supporting Evidence",
    SectionType.OPPOSING: "Opposing Evidence",
    SectionType.LIMITATIONS: "Limitations",
}


class ValidationErrorCode(StrEnum):
    LEDGER_MISMATCH = "ledger_mismatch"
    INVALID_SECTION = "invalid_section"
    INVALID_TEMPLATE = "invalid_template"
    ALTERED_STATEMENT = "altered_statement"
    SCHEMA_ERROR = "schema_error"


def _validate_aware_datetime(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("datetime values must be timezone-aware")
    return value


def _validate_offsets(
    offsets: list[SegmentOffset] | tuple[SegmentOffset, ...],
) -> list[SegmentOffset] | tuple[SegmentOffset, ...]:
    previous_end: int | None = None
    for offset in offsets:
        if previous_end is not None and offset.start_char < previous_end:
            raise ValueError("segment offsets must be ordered and non-overlapping")
        previous_end = offset.end_char
    return offsets


def _is_ledger_eligible(evidence_quality: int, claim_fit: int) -> bool:
    return evidence_quality >= 2 and claim_fit >= 3 and evidence_quality + claim_fit >= 5


def _derive_ledger_score(evidence_quality: int, claim_fit: int) -> int:
    total_score = evidence_quality + claim_fit
    if total_score <= 6:
        return 3
    if total_score <= 8:
        return 4
    return 5


def _expected_placement(evidence_quality: int, claim_fit: int) -> Placement:
    ledger_score = _derive_ledger_score(evidence_quality, claim_fit)
    if claim_fit == 3:
        return Placement.QUALIFIED_ONLY
    if ledger_score == 5:
        return Placement.PRIMARY
    if ledger_score == 4:
        return Placement.SECONDARY
    return Placement.SUPPORTING


class SegmentOffset(StrictModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    start_char: NonNegativeInt
    end_char: PositiveInt

    @model_validator(mode="after")
    def validate_order(self) -> SegmentOffset:
        if self.start_char >= self.end_char:
            raise ValueError("segment offset start_char must be before end_char")
        return self


class ClaimDefinition(StrictModel):
    run_id: UUID
    claim_text: NonEmptyStr
    population: NonEmptyStr
    jurisdiction: NonEmptyStr
    time_period: NonEmptyStr
    comparison_baseline: NonEmptyStr
    intervention_or_exposure: NonEmptyStr
    causal_or_comparative_meaning: NonEmptyStr
    created_at: datetime

    _created_at_is_aware = field_validator("created_at")(_validate_aware_datetime)


class AmbiguityRecord(StrictModel):
    run_id: UUID
    ambiguity_id: UUID
    description: NonEmptyStr
    impact: NonEmptyStr
    created_at: datetime

    _created_at_is_aware = field_validator("created_at")(_validate_aware_datetime)


class SearchQuery(StrictModel):
    run_id: UUID
    query_id: UUID
    stance: Stance
    provider: DiscoveryProvider = DiscoveryProvider.EXA
    intent: SearchIntent = SearchIntent.BROAD_WEB
    query_round: Annotated[int, Field(ge=1, le=3)]
    strategy: NonEmptyStr
    query_text: NonEmptyStr
    exclusion_parameters: str
    created_at: datetime

    _created_at_is_aware = field_validator("created_at")(_validate_aware_datetime)

    @model_validator(mode="after")
    def validate_provider_query(self) -> SearchQuery:
        if self.provider is DiscoveryProvider.EXA:
            missing = missing_required_query_exclusions(self.exclusion_parameters)
            if missing:
                raise ValueError("Exa query is missing required exclusion parameters")
        else:
            if self.intent is not SearchIntent.ACADEMIC_STUDY:
                raise ValueError("OpenAlex queries must use academic-study intent")
            if self.exclusion_parameters:
                raise ValueError("OpenAlex queries cannot contain web exclusion syntax")
        return self


class PlannerOutput(StrictModel):
    run_id: UUID
    claim_definition: ClaimDefinition
    ambiguities: list[AmbiguityRecord]
    search_queries: list[SearchQuery]
    planner_prompt_version: NonEmptyStr
    planner_model_name: NonEmptyStr
    planned_at: datetime

    _planned_at_is_aware = field_validator("planned_at")(_validate_aware_datetime)

    @model_validator(mode="after")
    def validate_queries(self) -> PlannerOutput:
        if self.claim_definition.run_id != self.run_id:
            raise ValueError("claim definition run_id must match planner run_id")
        for ambiguity in self.ambiguities:
            if ambiguity.run_id != self.run_id:
                raise ValueError("ambiguity run_id must match planner run_id")

        if len({query.query_id for query in self.search_queries}) != len(self.search_queries):
            raise ValueError("planner search query IDs must be unique")
        openalex_queries = [
            query for query in self.search_queries if query.provider is DiscoveryProvider.OPENALEX
        ]
        if not openalex_queries:
            self._validate_legacy_queries()
        else:
            self._validate_provider_specific_queries()
        for query in self.search_queries:
            if query.run_id != self.run_id:
                raise ValueError("search query run_id must match planner run_id")
        return self

    def _validate_legacy_queries(self) -> None:
        expected_rounds = {
            (Stance.SUPPORTING, 1),
            (Stance.SUPPORTING, 2),
            (Stance.SUPPORTING, 3),
            (Stance.OPPOSING, 1),
            (Stance.OPPOSING, 2),
            (Stance.OPPOSING, 3),
        }
        actual_rounds = {(query.stance, query.query_round) for query in self.search_queries}
        if len(self.search_queries) != 6 or actual_rounds != expected_rounds:
            raise ValueError(
                "new Planner output requires a separate OpenAlex lane; legacy output must "
                "contain exactly three supporting and three opposing Exa queries"
            )

    def _validate_provider_specific_queries(self) -> None:
        stances = {query.stance for query in self.search_queries}
        if Stance.SUPPORTING not in stances:
            raise ValueError("provider-specific Planner output requires supporting queries")
        for stance in stances:
            exa_rounds = {
                query.query_round
                for query in self.search_queries
                if query.stance is stance and query.provider is DiscoveryProvider.EXA
            }
            openalex = [
                query
                for query in self.search_queries
                if query.stance is stance and query.provider is DiscoveryProvider.OPENALEX
            ]
            if exa_rounds != {1, 2, 3} or len(openalex) != 1:
                raise ValueError(
                    "each active stance requires three Exa queries and one OpenAlex query"
                )
        expected_count = 8 if Stance.OPPOSING in stances else 4
        if len(self.search_queries) != expected_count:
            raise ValueError("provider-specific Planner output contains an unexpected query")

    @property
    def research_mode(self) -> ResearchMode:
        if any(query.stance is Stance.OPPOSING for query in self.search_queries):
            return ResearchMode.BALANCED
        return ResearchMode.FOCUSED

    def queries_for_provider(self, provider: DiscoveryProvider) -> tuple[SearchQuery, ...]:
        return tuple(query for query in self.search_queries if query.provider is provider)


class RetrievalRecord(StrictModel):
    run_id: UUID
    retrieval_attempt_id: UUID
    query_id: UUID
    query_round: Annotated[int, Field(ge=1, le=3)]
    query_text: NonEmptyStr
    search_rank: Annotated[int, Field(ge=1, le=25)]
    source_url: NonEmptyStr
    resolved_url: NonEmptyStr
    status: RetrievalStatus
    retrieved_at: datetime

    _retrieved_at_is_aware = field_validator("retrieved_at")(_validate_aware_datetime)


SupportedOriginMediaType = Literal["text/html", "text/plain", "application/pdf"]


class MediaTypeProvenance(StrictModel):
    """Keep verified origin evidence separate from provider-declared metadata."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    verified_media_type: SupportedOriginMediaType | None = None
    verified_source_url: str | None = None
    provider_declared_media_type: SupportedOriginMediaType | None = None

    @model_validator(mode="after")
    def validate_verified_pair(self) -> MediaTypeProvenance:
        if (self.verified_media_type is None) != (self.verified_source_url is None):
            raise ValueError("verified media type and source URL must be present together")
        if self.verified_source_url is not None and not self.verified_source_url.strip():
            raise ValueError("verified source URL cannot be blank")
        return self


class SourceSnapshot(StrictModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: UUID
    retrieval_attempt_id: UUID
    snapshot_id: UUID
    source_url: NonEmptyStr
    original_url: NonEmptyStr | None = None
    canonical_url: NonEmptyStr | None = None
    retrieved_at: datetime
    normalized_text: NonEmptyStr
    snapshot_sha256: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
    word_count: NonNegativeInt
    truncated: bool
    normalization_version: NonEmptyStr | None = None
    acquisition_version: NonEmptyStr | None = None
    provider_name: NonEmptyStr | None = None
    provider_version: NonEmptyStr | None = None
    media_type_provenance: MediaTypeProvenance = MediaTypeProvenance()
    created_at: datetime

    _retrieved_at_is_aware = field_validator("retrieved_at")(_validate_aware_datetime)
    _created_at_is_aware = field_validator("created_at")(_validate_aware_datetime)


class SelectedSentenceRange(StrictModel):
    """One inclusive, source-owned sentence range selected by the Extractor."""

    start_sentence: Annotated[int, Field(ge=1)]
    end_sentence: Annotated[int, Field(ge=1)]

    @model_validator(mode="after")
    def validate_order(self) -> SelectedSentenceRange:
        if self.end_sentence < self.start_sentence:
            raise ValueError("sentence range end must not precede its start")
        return self


class VerbatimQuoteSelection(StrictModel):
    """Minimal model-owned Extractor result; application code owns quote assembly."""

    selected_segments: tuple[NonEmptyStr, ...] = ()
    selected_sentence_ranges: tuple[SelectedSentenceRange, ...] = ()

    @field_validator("selected_segments")
    @classmethod
    def validate_exact_segments(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if any(segment != segment.strip() for segment in value):
            raise ValueError("selected quote segments cannot have surrounding whitespace")
        if any(not segment.strip() for segment in value):
            raise ValueError("selected quote segments must contain visible text")
        return value

    @model_validator(mode="after")
    def validate_selection_shape(self) -> VerbatimQuoteSelection:
        if bool(self.selected_segments) == bool(self.selected_sentence_ranges):
            raise ValueError("select either exact segments or source sentence ranges")
        previous_end = 0
        for selection_range in self.selected_sentence_ranges:
            if selection_range.start_sentence <= previous_end:
                raise ValueError("sentence ranges must be ordered and non-overlapping")
            previous_end = selection_range.end_sentence
        return self


class ProvisionalCandidate(StrictModel):
    run_id: UUID
    stance: Stance
    source_url: NonEmptyStr
    retrieval_attempt_id: UUID
    query_id: UUID
    query_round: Annotated[int, Field(ge=1, le=3)]
    search_rank: Annotated[int, Field(ge=1, le=25)]
    snapshot_id: UUID
    snapshot_sha256: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
    extracted_quote_block: NonEmptyStr
    extraction_prompt_version: NonEmptyStr
    extraction_model_name: NonEmptyStr
    extracted_at: datetime

    _extracted_at_is_aware = field_validator("extracted_at")(_validate_aware_datetime)


class CandidateQuoteBlock(StrictModel):
    run_id: UUID
    stance: Stance
    quote_block_id: UUID
    source_url: NonEmptyStr
    retrieval_attempt_id: UUID
    query_id: UUID
    query_round: Annotated[int, Field(ge=1, le=3)]
    search_rank: Annotated[int, Field(ge=1, le=25)]
    retrieved_at: datetime
    snapshot_id: UUID
    snapshot_sha256: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
    snapshot_created_at: datetime
    extracted_quote_block: NonEmptyStr
    segment_offsets: Annotated[list[SegmentOffset], Field(min_length=1)]
    raw_segment_word_count: PositiveInt
    has_statistical_markers: bool
    claim_keyword_match_count: NonNegativeInt
    truncated: bool
    extraction_prompt_version: NonEmptyStr
    extraction_model_name: NonEmptyStr
    extracted_at: datetime
    post_filter_version: NonEmptyStr
    post_filter_validated_at: datetime

    _retrieved_at_is_aware = field_validator("retrieved_at")(_validate_aware_datetime)
    _snapshot_created_at_is_aware = field_validator("snapshot_created_at")(_validate_aware_datetime)
    _extracted_at_is_aware = field_validator("extracted_at")(_validate_aware_datetime)
    _post_filter_validated_at_is_aware = field_validator("post_filter_validated_at")(
        _validate_aware_datetime
    )
    _segment_offsets_are_ordered = field_validator("segment_offsets")(_validate_offsets)


class CandidateBatch(StrictModel):
    run_id: UUID
    stance: Stance
    query_round: Annotated[int, Field(ge=1, le=3)]
    candidates: list[CandidateQuoteBlock]
    created_at: datetime

    _created_at_is_aware = field_validator("created_at")(_validate_aware_datetime)

    @model_validator(mode="after")
    def validate_batch_members(self) -> CandidateBatch:
        for candidate in self.candidates:
            if candidate.run_id != self.run_id:
                raise ValueError("candidate run_id must match batch run_id")
            if candidate.stance is not self.stance:
                raise ValueError("candidate stance must match batch stance")
            if candidate.query_round != self.query_round:
                raise ValueError("candidate query_round must match batch query_round")
        return self


class ScoreDecision(StrictModel):
    run_id: UUID
    quote_block_id: UUID
    evidence_quality: Score
    claim_fit: Score
    ledger_score: ApprovedScore | None = None
    placement: Placement | None = None
    approved: bool
    rationale: NonEmptyStr
    analyst_prompt_version: NonEmptyStr
    analyst_model_name: NonEmptyStr
    scored_at: datetime

    _scored_at_is_aware = field_validator("scored_at")(_validate_aware_datetime)

    @model_validator(mode="after")
    def validate_approval_and_placement(self) -> ScoreDecision:
        eligible = _is_ledger_eligible(self.evidence_quality, self.claim_fit)
        if not eligible:
            if self.approved:
                raise ValueError("ineligible score combinations cannot be approved")
            if self.ledger_score is not None or self.placement is not None:
                raise ValueError("ineligible score decisions must not assign Ledger fields")
            return self

        if self.approved:
            expected_score = _derive_ledger_score(self.evidence_quality, self.claim_fit)
            expected_placement = _expected_placement(self.evidence_quality, self.claim_fit)
            if self.ledger_score != expected_score:
                raise ValueError("approved score decisions require the derived Ledger score")
            if self.placement is not expected_placement:
                raise ValueError("approved score decisions require the derived placement")
        elif self.ledger_score is not None or self.placement is not None:
            raise ValueError("rejected score decisions must not assign Ledger fields")
        return self


class StatementDraft(StrictModel):
    run_id: UUID
    statement_draft_id: UUID
    quote_block_id: UUID
    stance: Stance
    draft_statement: NonEmptyStr
    claim_fit: Score
    analyst_prompt_version: NonEmptyStr
    analyst_model_name: NonEmptyStr
    drafted_at: datetime

    _drafted_at_is_aware = field_validator("drafted_at")(_validate_aware_datetime)


class StatementReviewResult(StrictModel):
    run_id: UUID
    statement_draft_id: UUID
    quote_block_id: UUID
    approved: bool
    reviewer_approval_id: ReviewerApprovalId | None = None
    approved_factual_statement: NonEmptyStr | None = None
    failure_code: ReviewerFailureCode | None = None
    rationale: NonEmptyStr
    reviewer_prompt_version: NonEmptyStr
    reviewer_model_name: NonEmptyStr
    reviewed_at: datetime

    _reviewed_at_is_aware = field_validator("reviewed_at")(_validate_aware_datetime)

    @model_validator(mode="after")
    def validate_result_shape(self) -> StatementReviewResult:
        if self.approved:
            if self.reviewer_approval_id is None:
                raise ValueError("approved review results require reviewer_approval_id")
            if self.approved_factual_statement is None:
                raise ValueError("approved review results require an approved factual statement")
            if self.failure_code is not None:
                raise ValueError("approved review results cannot include a failure code")
        else:
            if self.failure_code is None:
                raise ValueError("rejected review results require a failure code")
            if self.reviewer_approval_id is not None:
                raise ValueError("rejected review results cannot include reviewer_approval_id")
            if self.approved_factual_statement is not None:
                raise ValueError("rejected review results cannot include an approved statement")
        return self


class LedgerRecord(StrictModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: UUID
    ledger_claim_id: UUID
    quote_block_id: UUID
    stance: Stance
    approved_factual_statement: NonEmptyStr
    approved_claim_text: NonEmptyStr
    evidence_quality: Score
    claim_fit: Score
    ledger_score: ApprovedScore
    placement: Placement
    entailment: Entailment
    source_url: NonEmptyStr
    retrieval_attempt_id: UUID
    snapshot_id: UUID
    snapshot_sha256: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
    segment_offsets: Annotated[tuple[SegmentOffset, ...], Field(min_length=1)]
    analyst_prompt_version: NonEmptyStr
    analyst_model_name: NonEmptyStr
    analyst_completed_at: datetime
    reviewer_prompt_version: NonEmptyStr
    reviewer_model_name: NonEmptyStr
    reviewed_at: datetime
    reviewer_approval_id: ReviewerApprovalId
    ledger_validated_at: datetime

    _segment_offsets_are_ordered = field_validator("segment_offsets")(_validate_offsets)
    _analyst_completed_at_is_aware = field_validator("analyst_completed_at")(
        _validate_aware_datetime
    )
    _reviewed_at_is_aware = field_validator("reviewed_at")(_validate_aware_datetime)
    _ledger_validated_at_is_aware = field_validator("ledger_validated_at")(_validate_aware_datetime)

    @model_validator(mode="after")
    def validate_score_contract(self) -> LedgerRecord:
        if not _is_ledger_eligible(self.evidence_quality, self.claim_fit):
            raise ValueError("Ledger records require eligible two-axis scores")
        if self.ledger_score != _derive_ledger_score(self.evidence_quality, self.claim_fit):
            raise ValueError("Ledger records require the derived Ledger score")
        if self.placement is not _expected_placement(self.evidence_quality, self.claim_fit):
            raise ValueError("Ledger records require the derived placement")
        if self.entailment is not entailment_for_claim_fit(self.claim_fit):
            raise ValueError("Ledger entailment must be derived from Claim Fit")
        return self


class SourceFamilyIdentity(StrictModel):
    """Deterministic audit identity for one underlying source family."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    source_family_id: UUID
    family_key: NonEmptyStr
    identification_basis: NonEmptyStr


class EvidenceTrailEntry(StrictModel):
    """Append-only, plain-language outcome for one discovered source."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    trail_entry_id: UUID
    run_id: UUID
    retrieval_attempt_id: UUID
    research_round: ResearchRound
    role: EvidenceRole
    source_title: NonEmptyStr
    source_domain: NonEmptyStr
    original_url: NonEmptyStr
    resolved_url: NonEmptyStr
    source_family: SourceFamilyIdentity | None = None
    retrieval_method: NonEmptyStr
    snapshot_status: NonEmptyStr
    outcome: EvidenceTrailOutcome
    explanation: NonEmptyStr
    technical_failure_code: str | None = None
    model_attempt_ids: tuple[UUID, ...] = ()
    accepted_statement: str | None = None
    accepted_quote: str | None = None
    snapshot_sha256: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")] | None = None
    cost_incurred: bool = False
    created_at: datetime

    _created_at_is_aware = field_validator("created_at")(_validate_aware_datetime)


class PortfolioItem(StrictModel):
    """One approved Ledger statement included in an evidence portfolio."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: UUID
    ledger_claim_id: UUID
    source_family_id: UUID
    role: EvidenceRole
    research_round: ResearchRound
    added_at: datetime

    _added_at_is_aware = field_validator("added_at")(_validate_aware_datetime)


class PortfolioCoverageAssessment(StrictModel):
    """Deterministic source-family coverage, never a claim of factual certainty."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: UUID
    approved_evidence_items: NonNegativeInt
    independent_source_families: NonNegativeInt
    supporting_families: NonNegativeInt
    opposing_or_limitation_families: NonNegativeInt
    duplicate_count: NonNegativeInt
    rejected_count: NonNegativeInt
    inaccessible_count: NonNegativeInt
    research_rounds: NonNegativeInt
    rating: CoverageRating
    stopping_reason: NonEmptyStr
    important_missing_evidence: tuple[str, ...] = ()
    assessed_at: datetime

    _assessed_at_is_aware = field_validator("assessed_at")(_validate_aware_datetime)


class PortfolioExpansionRequest(StrictModel):
    """Typed context that directs the one permitted targeted Planner round."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: UUID
    original_claim: NonEmptyStr
    approved_source_families: tuple[SourceFamilyIdentity, ...]
    supporting_coverage: NonNegativeInt
    opposing_or_limitation_coverage: NonNegativeInt
    rejected_sources: tuple[NonEmptyStr, ...]
    inaccessible_domains: tuple[NonEmptyStr, ...]
    duplicate_source_families: tuple[SourceFamilyIdentity, ...]
    attempted_queries: tuple[NonEmptyStr, ...]
    evidence_gaps: tuple[NonEmptyStr, ...]


class ResearchRoundStatus(StrEnum):
    """Persisted lifecycle state for one bounded MVP-11 research round."""

    PLANNED = "planned"
    RUNNING = "running"
    COMPLETED = "completed"
    CEILING_STOPPED = "ceiling_stopped"
    CANCELLED = "cancelled"
    FAILED = "failed"


class ResearchGovernorDecisionOutcome(StrEnum):
    """The only deterministic outcomes of the post-Round-2 Governor."""

    BEGIN_ROUND_THREE = "begin_round_three"
    FINALIZE = "finalize"


class ResearchGovernorReasonCode(StrEnum):
    """Stable, application-owned explanation code for an authorization decision."""

    ROUND_THREE_AUTHORIZED = "round_three_authorized"
    PORTFOLIO_COMPLETE = "portfolio_complete"
    DUPLICATE_HEAVY_ROUND_TWO = "duplicate_heavy_round_two"
    CONSECUTIVE_UNPRODUCTIVE_SOURCES = "consecutive_unproductive_sources"
    NO_MEANINGFUL_SEARCH_ANGLE = "no_meaningful_search_angle"
    INSUFFICIENT_RESERVED_BUDGET = "insufficient_reserved_budget"
    RUN_CANCELLED = "run_cancelled"
    TERMINAL_PROVIDER_FAILURE = "terminal_provider_failure"
    ROUND_LIMIT_REACHED = "round_limit_reached"


class ResearchTerminalOutcome(StrEnum):
    """The permitted terminal evidence outcomes after the final research round."""

    COMPLETE = "complete"
    LIMITED = "limited"
    INSUFFICIENT = "insufficient"
    CANCELLED = "cancelled"
    FAILED = "failed"


class ResearchRoundRecord(StrictModel):
    """Append-only plan and terminal state for exactly one permitted research round."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: UUID
    research_round: Annotated[int, Field(ge=1, le=3)]
    status: ResearchRoundStatus
    planned_query_count: NonNegativeInt
    planned_discovery_count: NonNegativeInt
    completed_query_count: NonNegativeInt = 0
    completed_discovery_count: NonNegativeInt = 0
    started_at: datetime
    completed_at: datetime | None = None
    stopping_reason: NonEmptyStr

    _started_at_is_aware = field_validator("started_at")(_validate_aware_datetime)
    _completed_at_is_aware = field_validator("completed_at")(_validate_aware_datetime)

    @model_validator(mode="after")
    def validate_terminal_timestamp(self) -> ResearchRoundRecord:
        terminal = {
            ResearchRoundStatus.COMPLETED,
            ResearchRoundStatus.CEILING_STOPPED,
            ResearchRoundStatus.CANCELLED,
            ResearchRoundStatus.FAILED,
        }
        if self.status in terminal and self.completed_at is None:
            raise ValueError("terminal research rounds require completed_at")
        if self.completed_at is not None and self.completed_at < self.started_at:
            raise ValueError("research round completion cannot precede its start")
        if self.completed_query_count > self.planned_query_count:
            raise ValueError("completed queries cannot exceed the planned workload")
        if self.completed_discovery_count > self.planned_discovery_count:
            raise ValueError("completed discoveries cannot exceed the planned workload")
        return self


class ResearchGovernorBudgetState(StrictModel):
    """Cumulative accounted usage and conservative Round-3 reservation evidence."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    model_calls_used: NonNegativeInt
    model_calls_remaining: NonNegativeInt
    retrievals_used: NonNegativeInt
    retrievals_remaining: NonNegativeInt
    conservative_tokens_used: NonNegativeInt | None = None
    tokens_remaining: NonNegativeInt | None = None
    conservative_cost_used_usd: ExactUSD | None = None
    cost_remaining_usd: ExactUSD | None = None
    round_three_model_calls_required: NonNegativeInt
    round_three_retrievals_required: NonNegativeInt
    round_three_tokens_required: NonNegativeInt | None = None
    round_three_cost_required_usd: ExactUSD | None = None
    full_round_three_reserved: bool


class ResearchGovernorPolicy(StrictModel):
    """Versioned fixed application policy; callers cannot raise the three-round cap."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    policy_version: Literal["mvp11-research-governor-v1"] = "mvp11-research-governor-v1"
    required_independent_families: Literal[3] = 3
    duplicate_heavy_rate: Annotated[float, Field(ge=0, le=1)] = 0.70
    consecutive_unproductive_source_limit: Literal[3] = 3
    maximum_research_rounds: Literal[3] = 3


class ResearchGovernorEvaluationInput(StrictModel):
    """Typed facts used by deterministic application logic after completed Round 2."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: UUID
    current_round: Literal[2] = 2
    independent_approved_family_count: NonNegativeInt
    round_two_duplicate_count: NonNegativeInt
    round_two_result_count: NonNegativeInt
    consecutive_unproductive_source_count: NonNegativeInt
    remaining_search_angles: tuple[NonEmptyStr, ...]
    cumulative_budget: ResearchGovernorBudgetState
    cancelled: bool = False
    terminal_provider_or_infrastructure_failure: bool = False
    decided_at: datetime

    _decided_at_is_aware = field_validator("decided_at")(_validate_aware_datetime)

    @model_validator(mode="after")
    def validate_duplicate_count(self) -> ResearchGovernorEvaluationInput:
        if self.round_two_duplicate_count > self.round_two_result_count:
            raise ValueError("duplicate count cannot exceed completed Round-2 results")
        return self


class ResearchGovernorDecision(StrictModel):
    """Strict deterministic post-Round-2 authorization artifact."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: UUID
    current_round: Annotated[int, Field(ge=1, le=3)]
    independent_approved_family_count: NonNegativeInt
    portfolio_complete: bool
    round_two_duplicate_count: NonNegativeInt
    round_two_result_count: NonNegativeInt
    round_two_duplicate_rate: Annotated[float, Field(ge=0, le=1)]
    consecutive_unproductive_source_count: NonNegativeInt
    remaining_search_angles: tuple[NonEmptyStr, ...]
    cumulative_budget: ResearchGovernorBudgetState
    decision: ResearchGovernorDecisionOutcome
    reason_code: ResearchGovernorReasonCode
    explanation: NonEmptyStr
    policy_version: NonEmptyStr
    decided_at: datetime

    _decided_at_is_aware = field_validator("decided_at")(_validate_aware_datetime)

    @model_validator(mode="after")
    def validate_decision_contract(self) -> ResearchGovernorDecision:
        if self.current_round != 2:
            raise ValueError("Research Governor authorization is evaluated only after Round 2")
        if self.round_two_result_count == 0 and self.round_two_duplicate_rate != 0:
            raise ValueError("an empty Round 2 must have a zero duplicate rate")
        if self.decision is ResearchGovernorDecisionOutcome.BEGIN_ROUND_THREE:
            if self.reason_code is not ResearchGovernorReasonCode.ROUND_THREE_AUTHORIZED:
                raise ValueError("Round 3 authorization requires its stable reason code")
            if not self.cumulative_budget.full_round_three_reserved:
                raise ValueError("Round 3 authorization requires a full conservative reservation")
        elif self.reason_code is ResearchGovernorReasonCode.ROUND_THREE_AUTHORIZED:
            raise ValueError("finalization cannot use the authorization reason code")
        return self


class ResearchTerminalResult(StrictModel):
    """Terminal Governor summary that explains the permitted stopping point."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: UUID
    outcome: ResearchTerminalOutcome
    completed_rounds: Annotated[int, Field(ge=1, le=3)]
    independent_approved_family_count: NonNegativeInt
    explanation: NonEmptyStr
    finalized_at: datetime

    _finalized_at_is_aware = field_validator("finalized_at")(_validate_aware_datetime)


class SynthesisItem(StrictModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    connective_template_id: NonEmptyStr
    ledger_claim_id: UUID
    reviewer_approval_id: ReviewerApprovalId
    stance: Stance
    placement: Placement
    entailment: Entailment
    approved_factual_statement: NonEmptyStr


class SynthesisSection(StrictModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    section_type: SectionType
    items: tuple[SynthesisItem, ...]

    @model_validator(mode="after")
    def validate_item_compatibility(self) -> SynthesisSection:
        if self.section_type is SectionType.SUPPORTING:
            required_stance = Stance.SUPPORTING
        elif self.section_type is SectionType.OPPOSING:
            required_stance = Stance.OPPOSING
        else:
            return self

        for item in self.items:
            if item.stance is not required_stance:
                raise ValueError("section items must use a compatible stance")
        return self


class SynthesisOutput(StrictModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: UUID
    synthesizer_prompt_version: NonEmptyStr
    synthesizer_model_name: NonEmptyStr
    created_at: datetime
    sections: tuple[SynthesisSection, ...]

    _created_at_is_aware = field_validator("created_at")(_validate_aware_datetime)


class ValidationError(StrictModel):
    code: ValidationErrorCode
    location: NonEmptyStr
    message: NonEmptyStr


class ValidationResult(StrictModel):
    run_id: UUID
    valid: bool
    errors: list[ValidationError]
    validator_config_version: NonEmptyStr
    validated_at: datetime
    rendered_brief_hash: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")] | None = None

    _validated_at_is_aware = field_validator("validated_at")(_validate_aware_datetime)

    @model_validator(mode="after")
    def validate_result(self) -> ValidationResult:
        if self.valid and self.errors:
            raise ValueError("valid results cannot include errors")
        if self.valid and self.rendered_brief_hash is None:
            raise ValueError("valid results require rendered_brief_hash")
        if not self.valid and not self.errors:
            raise ValueError("invalid results require at least one validation error")
        if not self.valid and self.rendered_brief_hash is not None:
            raise ValueError("invalid results cannot include rendered_brief_hash")
        return self


class RunManifest(StrictModel):
    run_id: UUID
    status: RunStatus
    raw_claim: NonEmptyStr
    current_stage: Stage
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None = None

    _created_at_is_aware = field_validator("created_at")(_validate_aware_datetime)
    _updated_at_is_aware = field_validator("updated_at")(_validate_aware_datetime)
    _completed_at_is_aware = field_validator("completed_at")(_validate_aware_datetime)

    @model_validator(mode="after")
    def validate_completion(self) -> RunManifest:
        if self.status is RunStatus.COMPLETED and self.completed_at is None:
            raise ValueError("completed runs require completed_at")
        return self


class OrchestrationCheckpoint(StrictModel):
    run_id: UUID
    stage_key: NonEmptyStr
    status: CheckpointStatus
    failure_reason: NonEmptyStr | None = None
    updated_at: datetime

    _updated_at_is_aware = field_validator("updated_at")(_validate_aware_datetime)

    @model_validator(mode="after")
    def validate_status_shape(self) -> OrchestrationCheckpoint:
        if self.status is CheckpointStatus.FAILED and self.failure_reason is None:
            raise ValueError("failed checkpoints require a failure reason")
        if self.status is not CheckpointStatus.FAILED and self.failure_reason is not None:
            raise ValueError("only failed checkpoints may carry a failure reason")
        return self


class PersistedStageArtifact(StrictModel):
    run_id: UUID
    artifact_key: NonEmptyStr
    artifact_type: NonEmptyStr
    payload_json: NonEmptyStr
    created_at: datetime

    _created_at_is_aware = field_validator("created_at")(_validate_aware_datetime)


class ProviderRunContract(StrictModel):
    """Immutable compatibility identity required to create or resume a provider run."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: UUID
    fingerprint_sha256: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
    provider_identity: NonEmptyStr
    adapter_identity: NonEmptyStr
    model_identity: NonEmptyStr
    prompt_identity: NonEmptyStr
    schema_identity: NonEmptyStr
    normalization_identity: NonEmptyStr
    policy_identity: NonEmptyStr
    repository_revision: NonEmptyStr
    payload_json: NonEmptyStr
    created_at: datetime

    _created_at_is_aware = field_validator("created_at")(_validate_aware_datetime)

    @model_validator(mode="after")
    def validate_canonical_identity(self) -> ProviderRunContract:
        payload = parse_provider_contract_payload(self.payload_json)
        for field_name in (
            "provider_identity",
            "adapter_identity",
            "model_identity",
            "prompt_identity",
            "schema_identity",
            "normalization_identity",
            "policy_identity",
            "repository_revision",
        ):
            if payload[field_name] != getattr(self, field_name):
                raise ValueError(f"payload_json {field_name} does not match duplicated field")
        expected_fingerprint = provider_contract_fingerprint(self.payload_json)
        if self.fingerprint_sha256 != expected_fingerprint:
            raise ValueError(
                "fingerprint_sha256 does not match the canonical provider contract payload"
            )
        return self


class ModelUsageAccounting(StrictModel):
    """Exact totals, known subtotals, and conservative exposure for model attempts."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    exact_total_tokens: NonNegativeInt | None
    exact_total_cost_usd: ExactUSD | None
    known_token_subtotal: NonNegativeInt
    known_cost_subtotal_usd: ExactUSD
    token_complete: bool
    cost_complete: bool
    missing_token_attempt_ids: tuple[UUID, ...] = ()
    missing_cost_attempt_ids: tuple[UUID, ...] = ()
    conservative_reserved_tokens: NonNegativeInt | None
    conservative_reserved_cost_usd: ExactUSD | None

    @model_validator(mode="after")
    def validate_completeness(self) -> ModelUsageAccounting:
        if self.token_complete != (not self.missing_token_attempt_ids):
            raise ValueError("token completeness must match missing token attempts")
        if self.cost_complete != (not self.missing_cost_attempt_ids):
            raise ValueError("cost completeness must match missing cost attempts")
        if self.token_complete:
            if self.exact_total_tokens != self.known_token_subtotal:
                raise ValueError("complete token accounting requires its exact known subtotal")
        elif self.exact_total_tokens is not None:
            raise ValueError("incomplete token accounting cannot carry an exact total")
        if self.cost_complete:
            if self.exact_total_cost_usd != self.known_cost_subtotal_usd:
                raise ValueError("complete cost accounting requires its exact known subtotal")
        elif self.exact_total_cost_usd is not None:
            raise ValueError("incomplete cost accounting cannot carry an exact total")
        return self


class ModelUsageMetadata(StrictModel):
    input_tokens: NonNegativeInt | None = None
    cached_input_tokens: NonNegativeInt | None = None
    uncached_input_tokens: NonNegativeInt | None = None
    output_tokens: NonNegativeInt | None = None
    total_tokens: NonNegativeInt | None = None
    cost_usd: ExactUSD | None = None

    @model_validator(mode="after")
    def validate_token_total(self) -> ModelUsageMetadata:
        if (
            self.input_tokens is not None
            and self.output_tokens is not None
            and self.total_tokens is not None
            and self.total_tokens != self.input_tokens + self.output_tokens
        ):
            raise ValueError("total_tokens must equal input_tokens plus output_tokens")
        if self.cached_input_tokens is not None or self.uncached_input_tokens is not None:
            if (
                self.input_tokens is None
                or self.cached_input_tokens is None
                or self.uncached_input_tokens is None
                or self.cached_input_tokens + self.uncached_input_tokens != self.input_tokens
            ):
                raise ValueError(
                    "cached and uncached input tokens must exactly partition input_tokens"
                )
        return self


class ModelRouteAttempt(StrictModel):
    run_id: UUID
    operation_id: UUID
    attempt_id: UUID
    stage: NonEmptyStr
    output_type: NonEmptyStr
    model_alias: NonEmptyStr
    pinned_model_snapshot: NonEmptyStr | None = None
    route_index: NonNegativeInt
    attempt_number: PositiveInt
    input_artifact_ids: Annotated[tuple[UUID, ...], Field(min_length=1)]
    status: ModelAttemptStatus
    retry_reason: NonEmptyStr | None = None
    escalation_reason: NonEmptyStr | None = None
    failure_code: NonEmptyStr | None = None
    failure_reason: NonEmptyStr | None = None
    started_at: datetime
    ended_at: datetime | None = None
    latency_ms: Annotated[float, Field(ge=0.0)] | None = None
    reserved_tokens: NonNegativeInt | None = None
    reserved_cost_usd: ExactUSD | None = None
    usage: ModelUsageMetadata | None = None
    output_json: str | None = None

    _started_at_is_aware = field_validator("started_at")(_validate_aware_datetime)
    _ended_at_is_aware = field_validator("ended_at")(_validate_aware_datetime)

    @field_validator("input_artifact_ids")
    @classmethod
    def validate_input_artifact_ids(cls, value: tuple[UUID, ...]) -> tuple[UUID, ...]:
        if len(set(value)) != len(value):
            raise ValueError("input_artifact_ids must be unique")
        return value

    @model_validator(mode="after")
    def validate_attempt_shape(self) -> ModelRouteAttempt:
        if self.ended_at is not None and self.ended_at < self.started_at:
            raise ValueError("attempt ended_at cannot precede started_at")
        if self.status is ModelAttemptStatus.RUNNING:
            if any(
                value is not None
                for value in (
                    self.ended_at,
                    self.latency_ms,
                    self.failure_code,
                    self.failure_reason,
                    self.output_json,
                )
            ):
                raise ValueError("running attempts cannot carry completion fields")
            return self
        if self.ended_at is None or self.latency_ms is None:
            raise ValueError("finished attempts require end time and latency")
        if self.status is ModelAttemptStatus.COMPLETED:
            if self.output_json is None:
                raise ValueError("completed attempts require serialized typed output")
            if self.failure_code is not None or self.failure_reason is not None:
                raise ValueError("completed attempts cannot carry failure metadata")
        else:
            if self.failure_code is None or self.failure_reason is None:
                raise ValueError("failed attempts require failure code and reason")
        return self


class RunCancellationRequest(StrictModel):
    run_id: UUID
    requested_at: datetime
    reason: NonEmptyStr

    _requested_at_is_aware = field_validator("requested_at")(_validate_aware_datetime)


class ModelInvocationRecord(StrictModel):
    run_id: UUID
    invocation_id: UUID
    stage: Stage
    prompt_version: NonEmptyStr
    model_name: NonEmptyStr
    input_artifact_id: UUID
    output_artifact_id: UUID | None = None
    status: Literal["completed", "failed"]
    invoked_at: datetime

    _invoked_at_is_aware = field_validator("invoked_at")(_validate_aware_datetime)
