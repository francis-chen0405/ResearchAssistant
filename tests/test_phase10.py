from __future__ import annotations

import hashlib
import json
import shutil
from collections import defaultdict
from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import ValidationError

from evaluations.evaluator import (
    REQUIRED_FALLBACK_GATES,
    evaluate_corpus,
    load_corpus,
    render_human_summary,
    verify_summary_agreement,
    write_evaluation_outputs,
)
from evaluations.run_evaluations import main
from evaluations.schema import (
    CorpusManifest,
    IntegrityRegressionFixture,
    LiveComparisonStatus,
    LiveEvaluationObservation,
    LiveEvaluationRequest,
    MutationKind,
    MutationRegressionFixture,
    RouteOutcome,
)

ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT / "evaluations" / "cases" / "offline-corpus.json"
PHASE10_FIXTURES = ROOT / "tests" / "fixtures" / "phase10"


class RecordingLiveProvider:
    def __init__(self) -> None:
        self.requests: list[LiveEvaluationRequest] = []

    def evaluate(self, request: LiveEvaluationRequest) -> LiveEvaluationObservation:
        self.requests.append(request)
        return LiveEvaluationObservation(
            case_id=request.case_id,
            input_id=request.input_id,
            stage=request.stage,
            model_alias=request.model_alias,
            pinned_snapshot=request.pinned_snapshot,
            quality_score=0.75,
        )


def _load_payload() -> dict[str, object]:
    return json.loads(CORPUS.read_text(encoding="utf-8"))


def _write_mutated_corpus(tmp_path: Path, payload: dict[str, object]) -> Path:
    cases_dir = tmp_path / "cases"
    cases_dir.mkdir(parents=True)
    shutil.copytree(
        CORPUS.parent / "regression-fixtures",
        cases_dir / "regression-fixtures",
    )
    path = cases_dir / "corpus.json"
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def _rate_by_alias(report: object, alias: str) -> object:
    metrics = report.metrics.routes.by_alias  # type: ignore[attr-defined]
    return next(item for item in metrics if item.model_alias == alias)


def test_evaluation_runner_executes_offline_and_writes_both_outputs(tmp_path: Path) -> None:
    json_output = tmp_path / "results.json"
    summary_output = tmp_path / "summary.md"

    exit_code = main(
        [
            "--corpus",
            str(CORPUS),
            "--json-output",
            str(json_output),
            "--summary-output",
            str(summary_output),
        ]
    )

    assert exit_code == 0
    assert json_output.is_file()
    assert summary_output.is_file()
    assert json.loads(json_output.read_text(encoding="utf-8"))["passed"] is True
    assert "Status: **PASS**" in summary_output.read_text(encoding="utf-8")


def test_machine_and_human_outputs_are_derived_from_same_report(tmp_path: Path) -> None:
    report = evaluate_corpus(CORPUS)
    summary = render_human_summary(report)
    assert verify_summary_agreement(report, summary)

    json_path = tmp_path / "machine.json"
    summary_path = tmp_path / "summary.md"
    write_evaluation_outputs(report, json_path=json_path, summary_path=summary_path)

    machine = json.loads(json_path.read_text(encoding="utf-8"))
    human = summary_path.read_text(encoding="utf-8")
    assert machine["corpus_sha256"] in human
    assert f"Evaluated cases: {len(machine['evaluated_case_ids'])}" in human
    assert "Validator escape rate: 0.00%" in human
    assert machine["metrics"]["quality"]["input_kind"] == "frozen_evaluation_input"
    assert machine["metrics"]["costs"]["pricing_kind"] == "frozen_evaluation_input"
    assert "Frozen MiMo Pro minus MiMo normal quality delta: +0.050000" in human
    assert "Frozen Extractor DeepSeek Flash-minus-MiMo delta: -0.050000" in human
    assert "Total cost from frozen pricing with metadata: $0.011896000" in human


def test_metrics_include_every_required_phase10_surface() -> None:
    metrics = evaluate_corpus(CORPUS).model_dump(mode="json")["metrics"]
    assert set(metrics) == {
        "citation_accuracy",
        "snapshot_integrity",
        "bracket_accuracy",
        "safety",
        "decisions",
        "retrieval",
        "routes",
        "quality",
        "correlated_errors",
        "costs",
        "completion_time",
    }
    assert set(metrics["safety"]) == {
        "unsupported_claim_rate",
        "validator_escape_rate",
        "placement_consistency",
        "mutation_attack_block_rate",
        "prompt_injection_resistance",
    }


def test_integrity_metrics_classify_snapshot_citation_and_bracket_independently() -> None:
    report = evaluate_corpus(CORPUS)
    results = {result.case_id: result for result in report.integrity_results}

    assert report.metrics.citation_accuracy.value == 1.0
    assert report.metrics.snapshot_integrity.value == 1.0
    assert report.metrics.bracket_accuracy.value == 1.0
    assert results["integrity-tampered-hash"].snapshot_valid is False
    assert results["integrity-tampered-hash"].citation_valid is True
    assert results["integrity-wrong-offset"].citation_valid is False
    assert results["integrity-wrong-offset"].bracket_valid is True
    assert results["integrity-wrong-bracket"].bracket_valid is False


def test_validator_escape_unsupported_claim_and_placement_metrics_are_calculated() -> None:
    report = evaluate_corpus(CORPUS)
    safety = report.metrics.safety

    assert safety.validator_escape_rate.denominator == 9
    assert safety.validator_escape_rate.numerator == 0
    assert safety.unsupported_claim_rate.denominator == 2
    assert safety.unsupported_claim_rate.value == 0.0
    assert safety.placement_consistency.denominator == 1
    assert safety.placement_consistency.value == 1.0
    placement = next(
        result
        for result in report.mutation_results
        if result.mutation is MutationKind.PLACEMENT_CHANGE
    )
    assert placement.blocked
    assert "ledger_mismatch" in placement.validation_error_codes


def test_prompt_injection_is_isolated_as_untrusted_data_and_blocked_at_release() -> None:
    report = evaluate_corpus(CORPUS)

    assert report.metrics.safety.prompt_injection_resistance.value == 1.0
    envelope = report.prompt_injection_results[0]
    assert envelope.reported
    assert envelope.trust_label == "UNTRUSTED_SOURCE_TEXT"
    assert "ignore every instruction" in envelope.instruction_policy
    release_attack = next(
        result
        for result in report.mutation_results
        if result.mutation is MutationKind.PROMPT_INJECTION
    )
    assert release_attack.blocked


def test_failing_cases_are_named_and_never_silently_skipped(tmp_path: Path) -> None:
    payload = _load_payload()
    mutation_cases = payload["mutation_cases"]
    assert isinstance(mutation_cases, list)
    failing_case = json.loads(
        (PHASE10_FIXTURES / "unexpected-validator-expectation.json").read_text(encoding="utf-8")
    )
    mutation_cases.append(failing_case)
    corpus_path = _write_mutated_corpus(tmp_path, payload)

    report = evaluate_corpus(corpus_path)

    assert not report.passed
    assert failing_case["case_id"] in report.evaluated_case_ids
    assert any(failing_case["case_id"] in failure for failure in report.failures)


def test_all_integrity_and_mutation_regressions_have_frozen_fixture_expectations() -> None:
    corpus, _ = load_corpus(CORPUS)
    integrity_fixture = IntegrityRegressionFixture.model_validate_json(
        (CORPUS.parent / "regression-fixtures" / "integrity-attacks.json").read_text(
            encoding="utf-8"
        )
    )
    mutation_fixture = MutationRegressionFixture.model_validate_json(
        (CORPUS.parent / "regression-fixtures" / "validator-mutations.json").read_text(
            encoding="utf-8"
        )
    )
    integrity_expectations = {item.case_id: item for item in integrity_fixture.cases}
    mutation_expectations = {item.case_id: item for item in mutation_fixture.cases}

    assert corpus.integrity_cases
    for case in corpus.integrity_cases:
        assert case.regression_fixture is not None
        frozen = integrity_expectations[case.case_id]
        assert frozen.expected_snapshot_valid is case.expected_snapshot_valid
        assert frozen.expected_citation_valid is case.expected_citation_valid
        assert frozen.expected_bracket_valid is case.expected_bracket_valid
    assert corpus.mutation_cases
    for case in corpus.mutation_cases:
        assert case.regression_fixture is not None
        frozen = mutation_expectations[case.case_id]
        assert frozen.mutation is case.mutation
        assert frozen.expected_blocked is case.expected_blocked


def test_integrity_expectations_cannot_become_self_fulfilling(tmp_path: Path) -> None:
    payload = _load_payload()
    integrity_cases = payload["integrity_cases"]
    assert isinstance(integrity_cases, list)
    tampered = integrity_cases[1]
    tampered["tamper_snapshot_hash"] = False
    tampered["expected_snapshot_valid"] = True
    corpus_path = _write_mutated_corpus(tmp_path, payload)

    report = evaluate_corpus(corpus_path)

    assert not report.passed
    assert any(
        "integrity-tampered-hash" in failure and "frozen regression" in failure
        for failure in report.failures
    )


def test_integrity_and_mutation_cases_cannot_drop_regression_fixtures(
    tmp_path: Path,
) -> None:
    payload = _load_payload()
    integrity_cases = payload["integrity_cases"]
    assert isinstance(integrity_cases, list)
    integrity_cases[0]["regression_fixture"] = None
    corpus_path = _write_mutated_corpus(tmp_path, payload)

    report = evaluate_corpus(corpus_path)

    assert not report.passed
    assert any(
        "integrity-valid-control" in failure and "requires a frozen regression fixture" in failure
        for failure in report.failures
    )


def test_discovered_validator_failure_requires_a_regression_fixture(tmp_path: Path) -> None:
    payload = _load_payload()
    mutation_cases = payload["mutation_cases"]
    assert isinstance(mutation_cases, list)
    mutation_cases[1]["expected_blocked"] = False
    mutation_cases[1]["regression_fixture"] = None
    corpus_path = _write_mutated_corpus(tmp_path, payload)

    report = evaluate_corpus(corpus_path)

    assert not report.passed
    assert any("requires a regression fixture" in failure for failure in report.failures)


def test_evaluation_does_not_modify_or_weaken_existing_validator() -> None:
    validator_path = ROOT / "agents" / "renderer.py"
    before = hashlib.sha256(validator_path.read_bytes()).hexdigest()

    report = evaluate_corpus(CORPUS)

    after = hashlib.sha256(validator_path.read_bytes()).hexdigest()
    assert before == after
    assert report.metrics.safety.mutation_attack_block_rate.value == 1.0
    assert report.metrics.safety.validator_escape_rate.value == 0.0


def test_script_exit_codes_distinguish_pass_failure_and_execution_error(
    tmp_path: Path,
) -> None:
    passing = main(
        [
            "--corpus",
            str(CORPUS),
            "--json-output",
            str(tmp_path / "passing.json"),
            "--summary-output",
            str(tmp_path / "passing.md"),
        ]
    )
    payload = _load_payload()
    mutation_cases = payload["mutation_cases"]
    assert isinstance(mutation_cases, list)
    mutation_cases[1]["expected_blocked"] = False
    failing_corpus = _write_mutated_corpus(tmp_path / "failing", payload)
    failing = main(
        [
            "--corpus",
            str(failing_corpus),
            "--json-output",
            str(tmp_path / "failing.json"),
            "--summary-output",
            str(tmp_path / "failing.md"),
        ]
    )
    invalid = main(["--corpus", str(tmp_path / "does-not-exist.json")])

    assert passing == 0
    assert failing == 1
    assert invalid == 2
    assert "Status: **FAIL**" in (tmp_path / "failing.md").read_text(encoding="utf-8")


def test_script_exit_code_distinguishes_unexpected_internal_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def raise_unexpected(*args: object, **kwargs: object) -> object:
        raise AssertionError("unexpected evaluator defect")

    monkeypatch.setattr("evaluations.run_evaluations.evaluate_corpus", raise_unexpected)

    assert main(["--corpus", str(CORPUS)]) == 3


def test_same_corpus_produces_byte_identical_outputs(tmp_path: Path) -> None:
    first = evaluate_corpus(CORPUS)
    second = evaluate_corpus(CORPUS)
    assert first == second

    first_json = tmp_path / "first.json"
    first_summary = tmp_path / "first.md"
    second_json = tmp_path / "second.json"
    second_summary = tmp_path / "second.md"
    write_evaluation_outputs(first, json_path=first_json, summary_path=first_summary)
    write_evaluation_outputs(second, json_path=second_json, summary_path=second_summary)
    assert first_json.read_bytes() == second_json.read_bytes()
    assert first_summary.read_bytes() == second_summary.read_bytes()


def test_route_metrics_are_present_and_internally_consistent() -> None:
    report = evaluate_corpus(CORPUS)
    corpus, _ = load_corpus(CORPUS)
    expected_stages = {operation.stage for operation in corpus.route_operations}

    assert {stage.stage for stage in report.metrics.routes.by_stage} == expected_stages
    for stage in report.metrics.routes.by_stage:
        assert sum(item.count for item in stage.outcome_counts) == stage.attempts
        assert sum(item.count for item in stage.model_alias_counts) == stage.attempts
        assert stage.successful_operations <= stage.operations
        assert stage.primary_model_success_rate.denominator == stage.operations
        assert stage.retry_rate.denominator == stage.operations
        assert stage.fallback_rate.denominator == stage.operations


def test_impossible_route_alias_does_not_match_production_execution_path(
    tmp_path: Path,
) -> None:
    payload = _load_payload()
    route_operations = payload["route_operations"]
    assert isinstance(route_operations, list)
    reviewer_fallback = route_operations[3]
    reviewer_fallback["attempts"][-1]["model_alias"] = "deepseek-v4-flash"
    corpus_path = _write_mutated_corpus(tmp_path, payload)

    report = evaluate_corpus(corpus_path)

    assert not report.passed
    assert report.metrics.routes.default_route_matches.value < 1.0
    assert "frozen route differs from defaults" in report.failures


def test_fallback_route_requires_the_documented_single_retry() -> None:
    payload = _load_payload()
    route_operations = payload["route_operations"]
    assert isinstance(route_operations, list)
    reviewer_fallback = route_operations[3]
    del reviewer_fallback["attempts"][1]

    with pytest.raises(ValidationError, match="retry exhaustion"):
        CorpusManifest.model_validate(payload)


def test_fake_route_corpus_covers_primary_retry_and_approved_fallback_paths(
    tmp_path: Path,
) -> None:
    corpus, _ = load_corpus(CORPUS)

    assert any(
        len(operation.attempts) == 1 and operation.attempts[0].outcome is RouteOutcome.SUCCESS
        for operation in corpus.route_operations
    )
    assert any(
        any(attempt.attempt_number == 2 for attempt in operation.attempts)
        and all(attempt.route_index == 0 for attempt in operation.attempts)
        for operation in corpus.route_operations
    )
    assert any(
        any(
            attempt.route_index == 1 and attempt.outcome is RouteOutcome.SUCCESS
            for attempt in operation.attempts
        )
        for operation in corpus.route_operations
    )
    assert any(
        any(
            operation.stage == "extractor"
            and attempt.route_index == 1
            and attempt.outcome is RouteOutcome.SUCCESS
            for attempt in operation.attempts
        )
        for operation in corpus.route_operations
    )
    payload = _load_payload()
    route_operations = payload["route_operations"]
    assert isinstance(route_operations, list)
    route_operations.pop()
    report = evaluate_corpus(_write_mutated_corpus(tmp_path, payload))
    assert not report.passed
    assert "approved Extractor fallback-success route coverage is missing" in report.failures


def test_unsafe_fallback_fixture_forces_failure_and_cannot_bypass_gates(
    tmp_path: Path,
) -> None:
    payload = _load_payload()
    route_operations = payload["route_operations"]
    assert isinstance(route_operations, list)
    unsafe = json.loads(
        (PHASE10_FIXTURES / "unsafe-fallback-operation.json").read_text(encoding="utf-8")
    )
    route_operations.append(unsafe)
    corpus_path = _write_mutated_corpus(tmp_path, payload)

    report = evaluate_corpus(corpus_path)

    assert not report.passed
    assert report.metrics.routes.fallback_safety.value < 1.0
    assert "fallback bypassed one or more gates" in report.failures
    unsafe_gates = set(unsafe["attempts"][-1]["gates_passed"])
    assert not REQUIRED_FALLBACK_GATES.issubset(unsafe_gates)


def test_optional_live_comparison_is_skipped_unless_explicitly_enabled() -> None:
    report = evaluate_corpus(CORPUS)

    assert report.live_comparison.status is LiveComparisonStatus.SKIPPED
    assert report.live_comparison.observations == ()
    assert report.live_comparison.reason is not None
    with pytest.raises(ValueError, match="no live provider"):
        evaluate_corpus(CORPUS, live_enabled=True)


def test_live_comparison_uses_same_frozen_inputs_and_exact_alias_snapshots() -> None:
    provider = RecordingLiveProvider()
    corpus, _ = load_corpus(CORPUS)

    report = evaluate_corpus(CORPUS, live_enabled=True, live_provider=provider)

    assert report.live_comparison.status is LiveComparisonStatus.COMPLETED
    assert len(provider.requests) == sum(len(case.observations) for case in corpus.quality_cases)
    requests_by_input: defaultdict[str, list[LiveEvaluationRequest]] = defaultdict(list)
    for request in provider.requests:
        requests_by_input[request.input_id].append(request)
    for case in corpus.quality_cases:
        requests = requests_by_input[case.input_id]
        assert {request.frozen_input for request in requests} == {case.frozen_input}
        assert {(request.model_alias, request.pinned_snapshot) for request in requests} == {
            (observation.model_alias, observation.pinned_snapshot)
            for observation in case.observations
        }


def test_same_model_analyst_reviewer_correlated_errors_are_reported() -> None:
    report = evaluate_corpus(CORPUS)
    correlated = report.metrics.correlated_errors

    assert correlated.total_same_model_cases == 2
    assert correlated.correlated_error_count == 1
    assert correlated.reported_case_ids == ("correlated-same-model-scope-error",)
    assert "correlated-same-model-scope-error" in render_human_summary(report)


def test_cost_calculations_match_recorded_tokens_and_frozen_pricing() -> None:
    corpus, _ = load_corpus(CORPUS)
    pricing = {item.model_alias: item for item in corpus.pricing}
    expected = Decimal("0")
    for operation in corpus.route_operations:
        for attempt in operation.attempts:
            if attempt.input_tokens is None or attempt.output_tokens is None:
                continue
            rates = pricing[attempt.model_alias]
            expected += (
                Decimal(attempt.input_tokens) * Decimal(str(rates.input_usd_per_million))
                + Decimal(attempt.output_tokens) * Decimal(str(rates.output_usd_per_million))
            ) / Decimal(1_000_000)

    report = evaluate_corpus(CORPUS)
    costs = report.metrics.costs
    successful_artifacts = sum(item.successful_artifacts for item in corpus.route_operations)
    completed_runs = len({item.run_id for item in corpus.route_operations if item.completed_run})

    assert costs.total_cost_usd == pytest.approx(float(expected))
    assert costs.cost_per_successful_artifact_usd == pytest.approx(
        float(expected / successful_artifacts)
    )
    assert costs.cost_per_completed_run_usd == pytest.approx(float(expected / completed_runs))
    assert costs.attempts_with_token_metadata == costs.total_attempts


def test_failure_rates_are_reported_by_exact_model_alias() -> None:
    report = evaluate_corpus(CORPUS)
    pro = _rate_by_alias(report, "mimo-v2.5-pro")
    minimax = _rate_by_alias(report, "minimax-m3")

    assert pro.malformed_output_failure_rate.numerator == 2
    assert pro.exact_quote_failure_rate.numerator == 2
    assert minimax.malformed_output_failure_rate.value == 0.0
    assert minimax.exact_quote_failure_rate.value == 0.0


def test_quality_delta_uses_same_frozen_cases_and_includes_extractor_comparison() -> None:
    report = evaluate_corpus(CORPUS)

    assert report.metrics.quality.mimo_pro_minus_normal == pytest.approx(0.05)
    assert {item.stage for item in report.metrics.quality.by_stage} == {
        "planner",
        "extractor",
        "analyst",
        "reviewer",
        "synthesizer",
    }
    assert report.metrics.quality.extractor_deepseek_flash_minus_mimo == pytest.approx(-0.05)


def test_quality_cases_require_mimo_normal_and_pro_on_each_frozen_input() -> None:
    payload = _load_payload()
    quality_cases = payload["quality_cases"]
    assert isinstance(quality_cases, list)
    quality_cases[0]["observations"][1]["model_alias"] = "deepseek-v4-flash"

    with pytest.raises(ValidationError, match="MiMo normal and Pro"):
        CorpusManifest.model_validate(payload)

    missing_stage_payload = _load_payload()
    missing_stage_cases = missing_stage_payload["quality_cases"]
    assert isinstance(missing_stage_cases, list)
    missing_stage_cases.pop()
    with pytest.raises(ValidationError, match="missing required frozen stages"):
        CorpusManifest.model_validate(missing_stage_payload)


def test_token_metadata_requires_frozen_pricing_for_exact_alias() -> None:
    payload = _load_payload()
    route_operations = payload["route_operations"]
    assert isinstance(route_operations, list)
    route_operations[0]["attempts"][0]["model_alias"] = "unpriced-model"

    with pytest.raises(ValidationError, match="frozen pricing"):
        CorpusManifest.model_validate(payload)


def test_decision_and_correlated_error_cases_reject_contradictory_state() -> None:
    decision_payload = _load_payload()
    decision_cases = decision_payload["decision_cases"]
    assert isinstance(decision_cases, list)
    decision_cases[0]["reviewer_approved"] = True
    decision_cases[0]["reviewer_model_alias"] = "mimo-v2.5"
    with pytest.raises(ValidationError, match="Analyst-rejected"):
        CorpusManifest.model_validate(decision_payload)

    correlated_payload = _load_payload()
    correlated_cases = correlated_payload["correlated_error_cases"]
    assert isinstance(correlated_cases, list)
    correlated_cases[0]["analyst_error"] = False
    with pytest.raises(ValidationError, match="absent Analyst error"):
        CorpusManifest.model_validate(correlated_payload)

    missing_attack_payload = _load_payload()
    missing_attack_cases = missing_attack_payload["correlated_error_cases"]
    assert isinstance(missing_attack_cases, list)
    missing_attack_cases[0]["reviewer_failed_to_catch"] = False
    with pytest.raises(ValidationError, match="frozen same-model attack"):
        CorpusManifest.model_validate(missing_attack_payload)


def test_corpus_models_reject_unknown_fields() -> None:
    payload = _load_payload()
    payload["hidden_skip_failures"] = True

    with pytest.raises(ValidationError):
        CorpusManifest.model_validate(payload)
