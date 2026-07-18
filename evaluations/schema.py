from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Literal, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field, model_validator

NonEmptyStr = Annotated[str, Field(min_length=1)]
NonNegativeInt = Annotated[int, Field(ge=0)]
PositiveInt = Annotated[int, Field(ge=1)]
Rate = Annotated[float, Field(ge=0.0, le=1.0)]
MIMO_NORMAL_ALIAS = "mimo-v2.5"
MIMO_PRO_ALIAS = "mimo-v2.5-pro"
REQUIRED_QUALITY_STAGES = frozenset({"planner", "extractor", "analyst", "reviewer", "synthesizer"})


class EvaluationModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class RouteOutcome(StrEnum):
    SUCCESS = "success"
    TRANSIENT_FAILURE = "transient_failure"
    MALFORMED_OUTPUT = "malformed_output"
    EXACT_QUOTE_FAILURE = "exact_quote_failure"


class MutationKind(StrEnum):
    VALID_CONTROL = "valid_control"
    ALTERED_STATEMENT = "altered_statement"
    PUNCTUATION_CHANGE = "punctuation_change"
    CAPITALIZATION_CHANGE = "capitalization_change"
    PLACEMENT_CHANGE = "placement_change"
    REVIEWER_ID_CHANGE = "reviewer_id_change"
    LEDGER_ID_CHANGE = "ledger_id_change"
    UNKNOWN_TEMPLATE = "unknown_template"
    UNSUPPORTED_CLAIM = "unsupported_claim"
    PROMPT_INJECTION = "prompt_injection"


class LiveComparisonStatus(StrEnum):
    SKIPPED = "skipped"
    COMPLETED = "completed"


class IntegrityCase(EvaluationModel):
    case_id: NonEmptyStr
    normalized_text: NonEmptyStr
    quoted_segment: NonEmptyStr
    preceding_context: NonEmptyStr
    following_context: NonEmptyStr
    start_char: NonNegativeInt
    end_char: PositiveInt
    tamper_snapshot_hash: bool = False
    expected_snapshot_valid: bool
    expected_citation_valid: bool
    expected_bracket_valid: bool
    regression_fixture: NonEmptyStr | None = None

    @model_validator(mode="after")
    def validate_offset_order(self) -> IntegrityCase:
        if self.start_char >= self.end_char:
            raise ValueError("integrity case start_char must precede end_char")
        return self


class MutationCase(EvaluationModel):
    case_id: NonEmptyStr
    mutation: MutationKind
    expected_blocked: bool
    regression_fixture: NonEmptyStr | None = None


class IntegrityRegressionExpectation(EvaluationModel):
    case_id: NonEmptyStr
    expected_snapshot_valid: bool
    expected_citation_valid: bool
    expected_bracket_valid: bool


class IntegrityRegressionFixture(EvaluationModel):
    fixture_version: NonEmptyStr
    cases: Annotated[tuple[IntegrityRegressionExpectation, ...], Field(min_length=1)]

    @model_validator(mode="after")
    def validate_unique_case_ids(self) -> IntegrityRegressionFixture:
        case_ids = [case.case_id for case in self.cases]
        if len(case_ids) != len(set(case_ids)):
            raise ValueError("integrity regression fixture case IDs must be unique")
        return self


class MutationRegressionExpectation(EvaluationModel):
    case_id: NonEmptyStr
    mutation: MutationKind
    expected_blocked: bool


class MutationRegressionFixture(EvaluationModel):
    fixture_version: NonEmptyStr
    cases: Annotated[tuple[MutationRegressionExpectation, ...], Field(min_length=1)]

    @model_validator(mode="after")
    def validate_unique_case_ids(self) -> MutationRegressionFixture:
        case_ids = [case.case_id for case in self.cases]
        if len(case_ids) != len(set(case_ids)):
            raise ValueError("mutation regression fixture case IDs must be unique")
        return self


class PromptInjectionCase(EvaluationModel):
    case_id: NonEmptyStr
    untrusted_text: NonEmptyStr
    expected_reported: bool = True


class DecisionCase(EvaluationModel):
    case_id: NonEmptyStr
    evidence_quality: Annotated[int, Field(ge=1, le=5)]
    claim_fit: Annotated[int, Field(ge=1, le=5)]
    contested: bool
    analyst_approved: bool
    reviewer_approved: bool | None = None
    analyst_model_alias: NonEmptyStr
    reviewer_model_alias: NonEmptyStr | None = None

    @model_validator(mode="after")
    def validate_review_shape(self) -> DecisionCase:
        if not self.analyst_approved and self.reviewer_approved is not None:
            raise ValueError("Analyst-rejected cases cannot carry a Reviewer decision")
        if (self.reviewer_approved is None) != (self.reviewer_model_alias is None):
            raise ValueError("Reviewer decisions and model aliases must be provided together")
        return self


class RetrievalParityCase(EvaluationModel):
    case_id: NonEmptyStr
    supporting_attempts: NonNegativeInt
    opposing_attempts: NonNegativeInt
    supporting_successes: NonNegativeInt
    opposing_successes: NonNegativeInt

    @model_validator(mode="after")
    def validate_success_counts(self) -> RetrievalParityCase:
        if self.supporting_successes > self.supporting_attempts:
            raise ValueError("supporting successes cannot exceed attempts")
        if self.opposing_successes > self.opposing_attempts:
            raise ValueError("opposing successes cannot exceed attempts")
        return self


class RouteAttemptCase(EvaluationModel):
    model_alias: NonEmptyStr
    route_index: NonNegativeInt
    attempt_number: PositiveInt
    outcome: RouteOutcome
    input_tokens: NonNegativeInt | None = None
    output_tokens: NonNegativeInt | None = None
    gates_passed: tuple[NonEmptyStr, ...] = ()

    @model_validator(mode="after")
    def validate_token_pair(self) -> RouteAttemptCase:
        if (self.input_tokens is None) != (self.output_tokens is None):
            raise ValueError("route token metadata must provide input and output together")
        return self


class RouteOperationCase(EvaluationModel):
    case_id: NonEmptyStr
    run_id: NonEmptyStr
    stage: NonEmptyStr
    expected_primary_alias: NonEmptyStr
    attempts: Annotated[tuple[RouteAttemptCase, ...], Field(min_length=1)]
    successful_artifacts: NonNegativeInt
    completed_run: bool

    @model_validator(mode="after")
    def validate_attempt_order(self) -> RouteOperationCase:
        if self.attempts[0].route_index != 0 or self.attempts[0].attempt_number != 1:
            raise ValueError("route operations must begin with primary attempt one")
        successes = sum(attempt.outcome is RouteOutcome.SUCCESS for attempt in self.attempts)
        if successes > 1:
            raise ValueError("route operations may have at most one successful attempt")
        if self.successful_artifacts > 0 and successes != 1:
            raise ValueError("successful artifacts require one successful route attempt")
        aliases_by_route: dict[int, str] = {}
        attempt_numbers_by_route: dict[int, list[int]] = {}
        previous_route_index = 0
        for index, attempt in enumerate(self.attempts):
            if attempt.route_index < previous_route_index:
                raise ValueError("route indexes cannot move backward")
            if attempt.route_index > previous_route_index + 1:
                raise ValueError("route indexes cannot skip a configured fallback")
            previous_route_index = attempt.route_index
            existing_alias = aliases_by_route.setdefault(
                attempt.route_index,
                attempt.model_alias,
            )
            if existing_alias != attempt.model_alias:
                raise ValueError("one route index cannot refer to multiple aliases")
            attempt_numbers_by_route.setdefault(attempt.route_index, []).append(
                attempt.attempt_number
            )
            if attempt.outcome is RouteOutcome.SUCCESS and index != len(self.attempts) - 1:
                raise ValueError("route operations cannot continue after success")
        for attempt_numbers in attempt_numbers_by_route.values():
            if attempt_numbers != list(range(1, len(attempt_numbers) + 1)):
                raise ValueError("attempt numbers must be sequential within each route")
            if len(attempt_numbers) > 2:
                raise ValueError("route aliases permit at most one retry")
        for route_index in range(max(attempt_numbers_by_route)):
            if attempt_numbers_by_route[route_index] != [1, 2]:
                raise ValueError("fallback requires retry exhaustion on each earlier alias")
        return self


class QualityObservation(EvaluationModel):
    model_alias: NonEmptyStr
    pinned_snapshot: NonEmptyStr
    quality_score: Annotated[float, Field(ge=0.0, le=1.0)]
    malformed_output: bool = False
    exact_quote_failure: bool = False


class QualityCase(EvaluationModel):
    case_id: NonEmptyStr
    input_id: NonEmptyStr
    stage: NonEmptyStr
    frozen_input: NonEmptyStr
    observations: Annotated[tuple[QualityObservation, ...], Field(min_length=2)]

    @model_validator(mode="after")
    def validate_aliases(self) -> QualityCase:
        aliases = [observation.model_alias for observation in self.observations]
        if len(set(aliases)) != len(aliases):
            raise ValueError("quality observations require distinct aliases")
        if not {MIMO_NORMAL_ALIAS, MIMO_PRO_ALIAS}.issubset(aliases):
            raise ValueError(
                "quality cases require MiMo normal and Pro observations on each frozen input"
            )
        return self


class CorrelatedErrorCase(EvaluationModel):
    case_id: NonEmptyStr
    analyst_model_alias: NonEmptyStr
    reviewer_model_alias: NonEmptyStr
    error_signature: NonEmptyStr
    analyst_error: bool
    reviewer_failed_to_catch: bool

    @model_validator(mode="after")
    def validate_error_shape(self) -> CorrelatedErrorCase:
        if self.reviewer_failed_to_catch and not self.analyst_error:
            raise ValueError("Reviewer cannot fail to catch an absent Analyst error")
        return self


class CompletionCase(EvaluationModel):
    case_id: NonEmptyStr
    completed: bool
    duration_seconds: Annotated[float, Field(ge=0.0)]


class AliasPricing(EvaluationModel):
    model_alias: NonEmptyStr
    input_usd_per_million: Annotated[float, Field(ge=0.0)]
    output_usd_per_million: Annotated[float, Field(ge=0.0)]


class CorpusManifest(EvaluationModel):
    corpus_version: NonEmptyStr
    evaluated_at: NonEmptyStr
    integrity_cases: tuple[IntegrityCase, ...]
    mutation_cases: tuple[MutationCase, ...]
    prompt_injection_cases: tuple[PromptInjectionCase, ...]
    decision_cases: tuple[DecisionCase, ...]
    retrieval_parity_cases: tuple[RetrievalParityCase, ...]
    route_operations: tuple[RouteOperationCase, ...]
    quality_cases: tuple[QualityCase, ...]
    correlated_error_cases: tuple[CorrelatedErrorCase, ...]
    completion_cases: tuple[CompletionCase, ...]
    pricing: tuple[AliasPricing, ...]

    @model_validator(mode="after")
    def validate_case_ids(self) -> CorpusManifest:
        groups = (
            self.integrity_cases,
            self.mutation_cases,
            self.prompt_injection_cases,
            self.decision_cases,
            self.retrieval_parity_cases,
            self.route_operations,
            self.quality_cases,
            self.correlated_error_cases,
            self.completion_cases,
        )
        case_ids = [case.case_id for group in groups for case in group]
        if len(case_ids) != len(set(case_ids)):
            raise ValueError("evaluation case IDs must be globally unique")
        aliases = [item.model_alias for item in self.pricing]
        if len(aliases) != len(set(aliases)):
            raise ValueError("pricing aliases must be unique")
        quality_input_ids = [case.input_id for case in self.quality_cases]
        if len(quality_input_ids) != len(set(quality_input_ids)):
            raise ValueError("quality input IDs must be unique")
        quality_stages = {case.stage for case in self.quality_cases}
        missing_quality_stages = sorted(REQUIRED_QUALITY_STAGES - quality_stages)
        if missing_quality_stages:
            raise ValueError(
                "quality corpus is missing required frozen stages: "
                + ", ".join(missing_quality_stages)
            )
        same_model_cases = [
            case
            for case in self.correlated_error_cases
            if case.analyst_model_alias == case.reviewer_model_alias
        ]
        if not same_model_cases:
            raise ValueError("correlated-error corpus requires same-model cases")
        if not any(
            case.analyst_error and case.reviewer_failed_to_catch for case in same_model_cases
        ):
            raise ValueError("correlated-error corpus requires a frozen same-model attack")
        priced_aliases = set(aliases)
        token_aliases = {
            attempt.model_alias
            for operation in self.route_operations
            for attempt in operation.attempts
            if attempt.input_tokens is not None
        }
        missing_pricing = sorted(token_aliases - priced_aliases)
        if missing_pricing:
            raise ValueError(
                "token metadata requires frozen pricing for exact aliases: "
                + ", ".join(missing_pricing)
            )
        return self


class RateMetric(EvaluationModel):
    numerator: NonNegativeInt
    denominator: NonNegativeInt
    value: Rate

    @model_validator(mode="after")
    def validate_ratio(self) -> RateMetric:
        expected = 0.0 if self.denominator == 0 else self.numerator / self.denominator
        if abs(self.value - expected) > 1e-9:
            raise ValueError("rate value must agree with numerator and denominator")
        return self


class CountMetric(EvaluationModel):
    name: NonEmptyStr
    count: NonNegativeInt


class IntegrityCaseResult(EvaluationModel):
    case_id: NonEmptyStr
    snapshot_valid: bool
    citation_valid: bool
    bracket_valid: bool
    matched_expected: bool
    regression_fixture: NonEmptyStr | None = None


class MutationCaseResult(EvaluationModel):
    case_id: NonEmptyStr
    mutation: MutationKind
    blocked: bool
    expected_blocked: bool
    matched_expected: bool
    validation_error_codes: tuple[NonEmptyStr, ...]
    regression_fixture: NonEmptyStr | None = None


class PromptInjectionCaseResult(EvaluationModel):
    case_id: NonEmptyStr
    reported: bool
    matched_expected: bool
    trust_label: NonEmptyStr
    instruction_policy: NonEmptyStr


class StageRouteMetrics(EvaluationModel):
    stage: NonEmptyStr
    operations: NonNegativeInt
    attempts: NonNegativeInt
    successful_operations: NonNegativeInt
    primary_model_success_rate: RateMetric
    retry_rate: RateMetric
    fallback_rate: RateMetric
    outcome_counts: tuple[CountMetric, ...]
    model_alias_counts: tuple[CountMetric, ...]


class AliasFailureMetrics(EvaluationModel):
    model_alias: NonEmptyStr
    attempts: NonNegativeInt
    malformed_output_failure_rate: RateMetric
    exact_quote_failure_rate: RateMetric


class RouteMetrics(EvaluationModel):
    by_stage: tuple[StageRouteMetrics, ...]
    by_alias: tuple[AliasFailureMetrics, ...]
    fallback_safety: RateMetric
    default_route_matches: RateMetric


class DecisionMetrics(EvaluationModel):
    analyst_rejection_rate: RateMetric
    reviewer_rejection_rate: RateMetric
    score_separation: RateMetric


class RetrievalMetrics(EvaluationModel):
    retrieval_parity: RateMetric
    total_supporting_attempts: NonNegativeInt
    total_opposing_attempts: NonNegativeInt


class SafetyMetrics(EvaluationModel):
    unsupported_claim_rate: RateMetric
    validator_escape_rate: RateMetric
    placement_consistency: RateMetric
    mutation_attack_block_rate: RateMetric
    prompt_injection_resistance: RateMetric


class QualityDelta(EvaluationModel):
    stage: NonEmptyStr
    cases: PositiveInt
    pro_minus_normal: float


class QualityMetrics(EvaluationModel):
    input_kind: Literal["frozen_evaluation_input"] = "frozen_evaluation_input"
    mimo_pro_minus_normal: float
    by_stage: tuple[QualityDelta, ...]
    extractor_deepseek_flash_minus_mimo: float | None


class CorrelatedErrorMetrics(EvaluationModel):
    total_same_model_cases: NonNegativeInt
    correlated_error_count: NonNegativeInt
    reported_case_ids: tuple[NonEmptyStr, ...]


class CostMetrics(EvaluationModel):
    pricing_kind: Literal["frozen_evaluation_input"] = "frozen_evaluation_input"
    attempts_with_token_metadata: NonNegativeInt
    total_attempts: NonNegativeInt
    total_cost_usd: Annotated[float, Field(ge=0.0)] | None
    cost_per_successful_artifact_usd: Annotated[float, Field(ge=0.0)] | None
    cost_per_completed_run_usd: Annotated[float, Field(ge=0.0)] | None


class CompletionMetrics(EvaluationModel):
    completed_runs: NonNegativeInt
    average_seconds: Annotated[float, Field(ge=0.0)] | None
    maximum_seconds: Annotated[float, Field(ge=0.0)] | None


class EvaluationMetrics(EvaluationModel):
    citation_accuracy: RateMetric
    snapshot_integrity: RateMetric
    bracket_accuracy: RateMetric
    safety: SafetyMetrics
    decisions: DecisionMetrics
    retrieval: RetrievalMetrics
    routes: RouteMetrics
    quality: QualityMetrics
    correlated_errors: CorrelatedErrorMetrics
    costs: CostMetrics
    completion_time: CompletionMetrics


class LiveEvaluationRequest(EvaluationModel):
    case_id: NonEmptyStr
    input_id: NonEmptyStr
    stage: NonEmptyStr
    frozen_input: NonEmptyStr
    model_alias: NonEmptyStr
    pinned_snapshot: NonEmptyStr


class LiveEvaluationObservation(EvaluationModel):
    case_id: NonEmptyStr
    input_id: NonEmptyStr
    stage: NonEmptyStr
    model_alias: NonEmptyStr
    pinned_snapshot: NonEmptyStr
    quality_score: Annotated[float, Field(ge=0.0, le=1.0)]
    malformed_output: bool = False
    exact_quote_failure: bool = False


@runtime_checkable
class LiveEvaluationProvider(Protocol):
    def evaluate(self, request: LiveEvaluationRequest) -> LiveEvaluationObservation: ...


class LiveComparisonResult(EvaluationModel):
    status: LiveComparisonStatus
    reason: NonEmptyStr | None = None
    observations: tuple[LiveEvaluationObservation, ...] = ()

    @model_validator(mode="after")
    def validate_status_shape(self) -> LiveComparisonResult:
        if self.status is LiveComparisonStatus.SKIPPED:
            if self.reason is None or self.observations:
                raise ValueError("skipped live comparison requires a reason and no observations")
        elif self.reason is not None:
            raise ValueError("completed live comparison cannot carry a skip reason")
        return self


class EvaluationReport(EvaluationModel):
    evaluation_version: NonEmptyStr
    corpus_version: NonEmptyStr
    corpus_sha256: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
    evaluated_at: NonEmptyStr
    passed: bool
    metrics: EvaluationMetrics
    integrity_results: tuple[IntegrityCaseResult, ...]
    mutation_results: tuple[MutationCaseResult, ...]
    prompt_injection_results: tuple[PromptInjectionCaseResult, ...]
    live_comparison: LiveComparisonResult
    failures: tuple[NonEmptyStr, ...]
    evaluated_case_ids: tuple[NonEmptyStr, ...]
