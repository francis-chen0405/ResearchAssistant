"""Evaluate frozen observations locally, without credentials, networking or model calls."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from decimal import Decimal
from pathlib import Path
from typing import Any

from evaluations.observation_safety import validate_artifact_content, validate_observation_url
from evaluations.research_quality_contracts import (
    STAGES,
    Artifact,
    Benchmark,
    Candidate,
    FrozenReference,
    Observation,
    Topic,
)

DEFAULT_MANIFEST = Path(__file__).parent / "cases/research_quality/prepared.json"


def artifact_bytes(root: Path, artifact: Artifact) -> bytes:
    path = (root / artifact.path).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError("artifact escapes bundle, including through symlinks")
    payload = path.read_bytes()
    if hashlib.sha256(payload).hexdigest() != artifact.sha256:
        raise ValueError(f"frozen artifact checksum mismatch: {artifact.path}")
    return payload


def verify_artifacts(root: Path, observation: Observation) -> None:
    payloads = {a.path: artifact_bytes(root, a) for a in observation.artifacts}
    for artifact in observation.artifacts:
        validate_artifact_content(payloads[artifact.path], artifact.media_type)
    for attempt in observation.attempts:
        validate_observation_url(attempt.endpoint)
        validate_artifact_content(json.dumps(attempt.settings).encode(), "application/json")
    for candidate in observation.candidates:
        validate_observation_url(candidate.url)
    for statement in observation.statements:
        if statement.quote and statement.snapshot_path:
            text = payloads[statement.snapshot_path].decode("utf-8")
            if statement.quote not in text:
                raise ValueError("statement quotation is not exact in its frozen snapshot")
            owners = [c for c in observation.candidates if c.candidate_id in statement.source_ids]
            if not any(c.snapshot_path == statement.snapshot_path for c in owners):
                raise ValueError("statement snapshot does not belong to its cited source")
    for candidate in observation.candidates:
        judgment = candidate.judgment
        if (
            judgment
            and judgment.kind != "authored_fixture"
            and (judgment.useful is not None or judgment.relevant is not None)
        ):
            if (
                not candidate.snapshot_path
                or candidate.snapshot_path not in judgment.evidence_paths
            ):
                raise ValueError(
                    "content usefulness/relevance must inspect the frozen source snapshot"
                )
        if judgment and judgment.capture in {"full_text", "partial", "abstract_only"}:
            if (
                not candidate.snapshot_path
                or candidate.snapshot_path not in judgment.evidence_paths
            ):
                raise ValueError("readability judgment must inspect the owned snapshot")


def _ratio(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def _work_judgments(
    candidates: tuple[Candidate, ...], origin: str
) -> dict[str, tuple[bool | None, bool | None]]:
    # Filtering publication URLs cannot adjudicate conflicting work-level grades.
    groups: dict[str, tuple[set[bool], set[bool]]] = {}
    for candidate in candidates:
        useful, relevant = groups.setdefault(candidate.work_id, (set(), set()))
        judgment = candidate.judgment
        if judgment and judgment.kind == ("authored_fixture" if origin == "fixture" else "human"):
            if judgment.useful is not None:
                useful.add(judgment.useful)
            if judgment.relevant is not None:
                relevant.add(judgment.relevant)
    return {
        key: (
            next(iter(useful)) if len(useful) == 1 else None,
            next(iter(relevant)) if len(relevant) == 1 else None,
        )
        for key, (useful, relevant) in groups.items()
    }


def _assessment(
    candidates: list[Candidate], work_judgments: dict[str, tuple[bool | None, bool | None]]
) -> dict[str, Any]:
    works = {candidate.work_id for candidate in candidates}
    values = {work: work_judgments[work][0] for work in works}
    useful = sorted(key for key, value in values.items() if value is True)
    known = sum(value is not None for value in values.values())
    total = len(values)
    relevant_known = sum(work_judgments[work][1] is not None for work in works)
    relevant = sum(work_judgments[work][1] is True for work in works)
    return {
        "metric_scope": "recorded_work_inventory",
        "work_judgment_scope": "observation_inventory",
        "work_count": total,
        "judged_work_count": known,
        "useful_work_ids": useful,
        "precision": _ratio(len(useful), total) if total == known else None,
        "judged_precision": _ratio(len(useful), known),
        "precision_lower_bound": _ratio(len(useful), total),
        "precision_upper_bound": _ratio(len(useful) + total - known, total),
        "judgment_coverage": _ratio(known, total),
        "relevance_precision": _ratio(relevant, total) if relevant_known == total else None,
        "relevance_judgment_coverage": _ratio(relevant_known, total),
    }


def evaluate_observation(topic: Topic, observation: Observation, k: int) -> dict[str, Any]:
    reference = {w.work_id for w in topic.reference.works}
    locked = topic.reference.status == "locked"
    work_judgments = _work_judgments(observation.candidates, observation.origin)
    stage_results: dict[str, Any] = {}
    for stage in STAGES:
        observed = [
            c for c in observation.candidates if any(d.stage == stage for d in c.dispositions)
        ]
        survivors = [
            c
            for c in observed
            if any(d.stage == stage and d.outcome == "kept" for d in c.dispositions)
        ]
        works = {c.work_id for c in survivors}
        assessment = _assessment(survivors, work_judgments)
        complete = observation.candidate_inventory_complete and all(
            any(d.stage == stage and d.outcome != "not_observed" for d in c.dispositions)
            for c in observation.candidates
        )
        stage_results[stage] = {
            **assessment,
            "observed_candidates": len(observed),
            "stage_inventory_complete": complete,
            "reference_hits": len(works & reference) if locked else None,
            "reference_denominator": len(reference) if locked else None,
            "reference_recall": _ratio(len(works & reference), len(reference))
            if locked and complete
            else None,
            "extra_useful_work_ids": sorted(set(assessment["useful_work_ids"]) - reference)
            if locked
            else None,
            "dispositions": dict(
                Counter(
                    f"{d.outcome}:{d.reason}"
                    for c in observed
                    for d in c.dispositions
                    if d.stage == stage
                )
            ),
        }
    ranked = sorted(observation.candidates, key=lambda c: (c.rank, c.candidate_id))[:k]
    # K is per physical query/page. Multi-query unions are reported separately.
    precision_at_k = []
    for attempt in observation.attempts:
        if attempt.category != "search":
            continue
        page = sorted(
            (c for c in observation.candidates if c.attempt_id == attempt.attempt_id),
            key=lambda c: (c.rank, c.candidate_id),
        )[:k]
        precision_at_k.append(
            {
                "attempt_id": attempt.attempt_id,
                "requested_k": k,
                "returned_at_k": len(page),
                **_assessment(page, work_judgments),
            }
        )
    judgments = [
        c.judgment
        for c in observation.candidates
        if c.judgment
        and c.judgment.kind == ("authored_fixture" if observation.origin == "fixture" else "human")
    ]
    full_text = {
        c.work_id
        for c in observation.candidates
        if c.judgment in judgments and c.judgment and c.judgment.capture == "full_text"
    }
    usable_states = sum(j.capture != "unknown" for j in judgments)
    studies = {j.study_id for j in judgments if j.study_id}
    judged_statements = [
        s
        for s in observation.statements
        if s.entailment != "unknown"
        and s.reviewer_kind == ("authored_fixture" if observation.origin == "fixture" else "human")
    ]
    supported = sum(s.entailment == "supported" for s in judged_statements)
    total_statements = len(observation.statements)
    actual_known = sum(a.actual_usd is not None for a in observation.attempts)
    known_cost = sum((a.actual_usd or Decimal(0) for a in observation.attempts), Decimal(0))
    exposure = sum(
        (max(a.reserved_usd, a.actual_usd or Decimal(0)) for a in observation.attempts), Decimal(0)
    )
    elapsed = (
        (observation.completed_at - observation.started_at).total_seconds()
        if observation.completed_at
        else None
    )
    admission = stage_results["admission"]
    admission_utility_status = "untested"
    if admission["judged_work_count"]:
        admission_utility_status = (
            "evaluated"
            if admission["stage_inventory_complete"]
            and admission["judged_work_count"] == admission["work_count"]
            else "partial"
        )
    admission_behavior_observed = any(
        d.stage == "admission" and d.outcome != "not_observed"
        for c in observation.candidates
        for d in c.dispositions
    )
    work_urls: dict[str, set[str]] = {}
    for candidate in observation.candidates:
        work_urls.setdefault(candidate.work_id, set()).add(candidate.url)
    return {
        "observation_id": observation.observation_id,
        "topic_id": topic.topic_id,
        "split": topic.split,
        "arm": observation.arm,
        "origin": observation.origin,
        "source_identity": observation.source_identity,
        "settings_sha256": observation.settings_sha256,
        "input_sha256": observation.input_sha256,
        "reference_scope": topic.reference.scope,
        "reference_status": topic.reference.status,
        "global_useful_source_denominator": None,
        "stages": stage_results,
        "provider_precision_at_k": precision_at_k,
        "ranked_union_at_k_diagnostic": _assessment(ranked, work_judgments),
        "duplicate_urls": len(observation.candidates)
        - len({c.url for c in observation.candidates}),
        "publication_aliases": sum(len(urls) - 1 for urls in work_urls.values()),
        "resolved_study_groups": len(studies),
        "unresolved_study_candidates": len(observation.candidates)
        - sum(bool(j.study_id) for j in judgments),
        "capture_judgments_known": usable_states,
        "full_text_work_count": len(full_text),
        "full_text_reference_recall": _ratio(len(full_text & reference), len(reference))
        if locked
        and usable_states == len(observation.candidates)
        and observation.candidate_inventory_complete
        else None,
        "final_statements": total_statements,
        "final_inventory_complete": observation.final_inventory_complete,
        "judged_final_statements": len(judged_statements),
        "supported_final_statement_rate": _ratio(supported, total_statements)
        if observation.final_inventory_complete and len(judged_statements) == total_statements
        else None,
        "supported_statement_lower_bound": _ratio(supported, total_statements)
        if observation.final_inventory_complete
        else None,
        "supported_statement_upper_bound": _ratio(
            supported + total_statements - len(judged_statements), total_statements
        )
        if observation.final_inventory_complete
        else None,
        "recorded_subset_supported_statement_lower_bound": _ratio(supported, total_statements),
        "recorded_subset_supported_statement_upper_bound": _ratio(
            supported + total_statements - len(judged_statements), total_statements
        ),
        "recorded_subset_statement_scope": "recorded_final_statements",
        "admission_behavior_observed": admission_behavior_observed,
        "admission_utility_status": admission_utility_status,
        "physical_requests_by_category": dict(Counter(a.category for a in observation.attempts)),
        "model_inputs": [
            {
                "attempt_id": a.attempt_id,
                "stage": a.settings.get("stage"),
                "input_sha256": a.model_input.sha256,
                "settings": a.settings,
            }
            for a in observation.attempts
            if a.category == "model" and a.model_input
        ],
        "physical_audit_complete": observation.audit_complete,
        "known_model_token_subtotal": sum(
            a.tokens or 0 for a in observation.attempts if a.category == "model"
        ),
        "model_token_unknown_attempts": sum(
            a.tokens is None for a in observation.attempts if a.category == "model"
        ),
        "unknown_outcomes": sum(a.outcome == "unknown" for a in observation.attempts),
        "known_cost_subtotal_usd": str(known_cost),
        "actual_total_cost_usd": str(known_cost)
        if observation.audit_complete and actual_known == len(observation.attempts)
        else None,
        "recorded_exposure_usd": str(exposure),
        "cost_unknown_attempts": len(observation.attempts) - actual_known,
        "tokens": sum(a.tokens or 0 for a in observation.attempts if a.category == "model")
        if observation.audit_complete
        and all(a.tokens is not None for a in observation.attempts if a.category == "model")
        else None,
        "elapsed_seconds": elapsed,
    }


def replay_discovery(root: Path, observation: Observation, claim: str, k: int) -> dict[str, Any]:
    """Replay exact production handoffs through current normalization/ranking only."""
    from researchassistant.agents.v2_discovery import (
        V2DiscoveryResponse,
        normalize_discovery_responses,
    )
    from researchassistant.contracts.discovery_v2 import V2ProductDiscoveryPolicy
    from researchassistant.contracts.models import ResearchDirections
    from researchassistant.research.metadata_ranking import fair_ranked_ids, rank_metadata

    by_path = {a.path: a for a in observation.artifacts}
    responses = tuple(
        V2DiscoveryResponse.model_validate_json(artifact_bytes(root, by_path[p]))
        for p in observation.discovery_handoff_paths
    )
    if not responses:
        return {"status": "unavailable", "model_stages": "not_executed"}
    attempts = {attempt.attempt_id: attempt for attempt in observation.attempts}
    mapped_attempts = {
        identifier
        for identifiers in observation.discovery_handoff_attempts.values()
        for identifier in identifiers
    }
    if observation.candidate_inventory_complete:
        successful_searches = {
            attempt.attempt_id
            for attempt in observation.attempts
            if attempt.category == "search" and attempt.outcome == "success"
        }
        if mapped_attempts != successful_searches:
            raise ValueError("complete replay must represent every successful search attempt")
    for handoff_path, response in zip(observation.discovery_handoff_paths, responses, strict=True):
        attempt_ids = observation.discovery_handoff_attempts.get(handoff_path)
        if attempt_ids is None:
            # Historical handoffs without transport receipts stay explicitly incomplete.
            if observation.candidates:
                raise ValueError("candidate replay requires explicit query/attempt lineage")
            continue
        physical_results: Counter[str] = Counter()
        candidates = [c for c in observation.candidates if c.attempt_id in attempt_ids]
        for attempt_id in attempt_ids:
            attempt = attempts[attempt_id]
            if attempt.outcome != "success" or (
                attempt.settings.get("query_id") != str(response.query.query_id)
                or attempt.provider != response.query.provider.value
            ):
                raise ValueError("handoff query/provider differs from its owned successful attempt")
            result_path = observation.search_attempt_result_paths.get(attempt_id)
            if result_path is None:
                raise ValueError("physical search attempt lacks a frozen page-result projection")
            page = V2DiscoveryResponse.model_validate_json(
                artifact_bytes(root, by_path[result_path])
            )
            if page.query != response.query:
                raise ValueError("physical page query differs from its logical handoff")
            returned = Counter((item.original_url, item.rank) for item in page.results)
            recorded = Counter((c.url, c.rank) for c in candidates if c.attempt_id == attempt_id)
            if recorded - returned or (
                observation.candidate_inventory_complete and recorded != returned
            ):
                raise ValueError("query-specific candidate inventory differs from frozen page")
            physical_results.update(
                json.dumps(item.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
                for item in page.results
            )
        logical_results = Counter(
            json.dumps(item.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
            for item in response.results
        )
        if logical_results - physical_results:
            raise ValueError("logical handoff results lack physical page provenance")
        # The logical provider handoff precedes normalization/cluster retention.
        # Its exact subset may exclude cross-page duplicates or budget-trimmed
        # hits; later stage dispositions can drop additional works independently.
    if observation.candidates and any(
        candidate.attempt_id not in mapped_attempts for candidate in observation.candidates
    ):
        raise ValueError("candidate attempt is absent from the frozen handoff inventory")
    run_id = responses[0].query.run_id
    policy = V2ProductDiscoveryPolicy()
    rounds = []
    for round_number in sorted({r.query.round_number for r in responses}):
        items = normalize_discovery_responses(
            run_id=run_id,
            directions=ResearchDirections(support_enabled=True, challenge_enabled=True),
            responses=tuple(r for r in responses if r.query.round_number == round_number),
            discovered_at=observation.started_at,
        )
        ranks = rank_metadata(items, exact_claim=claim, policy=policy)
        selected = fair_ranked_ids(ranks, limit=k)
        rounds.append(
            {
                "round": round_number,
                "normalized_items": len(items),
                "selected_ids": [str(i) for i in selected],
            }
        )
    return {
        "status": "replayed",
        "origin": observation.origin,
        "normalized_items": sum(r["normalized_items"] for r in rounds),
        "rounds": rounds,
        "ranker_policy": policy.model_dump(mode="json"),
        "model_stages": "not_executed",
        "candidate_inventory_available": observation.candidate_inventory_complete,
        "query_attempt_lineage_verified": len(observation.discovery_handoff_attempts)
        == len(responses),
        "new_physical_requests": 0,
    }


def evaluate(path: Path, *, k: int = 10, replay: bool = False) -> dict[str, Any]:
    if not 1 <= k <= 25:
        raise ValueError("comparison K must be within the acquisition round ceiling")
    raw = path.read_bytes()
    validate_artifact_content(raw, "application/json")
    benchmark = Benchmark.model_validate_json(raw)
    topics = {t.topic_id: t for t in benchmark.topics}
    for topic in benchmark.topics:
        if topic.reference.evidence:
            payload = artifact_bytes(path.parent, topic.reference.evidence)
            validate_artifact_content(payload, topic.reference.evidence.media_type)
            if topic.reference.status == "locked":
                frozen = FrozenReference.model_validate_json(payload)
                expected = FrozenReference(
                    topic_id=topic.topic_id,
                    claim_sha256=hashlib.sha256(topic.claim.encode()).hexdigest(),
                    scope=topic.reference.scope,
                    method=topic.reference.method,
                    locked_at=topic.reference.locked_at,
                    reviewer=topic.reference.reviewer,
                    works=topic.reference.works,
                    supporting_evidence=topic.reference.supporting_evidence,
                )
                if frozen != expected:
                    raise ValueError("scored reference differs from its frozen reference artifact")
        for supporting in topic.reference.supporting_evidence:
            validate_artifact_content(
                artifact_bytes(path.parent, supporting), supporting.media_type
            )
    results = []
    for observation in benchmark.observations:
        if (
            hashlib.sha256(topics[observation.topic_id].claim.encode()).hexdigest()
            != observation.input_sha256
        ):
            raise ValueError("observation input digest differs from the exact frozen claim")
        verify_artifacts(path.parent, observation)
        result = evaluate_observation(topics[observation.topic_id], observation, k)
        if replay:
            result["discovery_replay"] = replay_discovery(
                path.parent, observation, topics[observation.topic_id].claim, k
            )
        results.append(result)
    comparisons = []
    for index, left in enumerate(results):
        for right in results[index + 1 :]:
            if (left["topic_id"], left["origin"]) != (right["topic_id"], right["origin"]):
                continue
            comparisons.append(
                {
                    "left": left["observation_id"],
                    "right": right["observation_id"],
                    "same_claim": left["input_sha256"] == right["input_sha256"],
                    "matched_model_inputs": [
                        {
                            "left_attempt": a["attempt_id"],
                            "right_attempt": b["attempt_id"],
                            "stage": a["stage"],
                            "input_sha256": a["input_sha256"],
                        }
                        for a in left["model_inputs"]
                        for b in right["model_inputs"]
                        if a["stage"] == b["stage"]
                        and a["stage"] is not None
                        and a["input_sha256"] == b["input_sha256"]
                    ],
                    "same_settings": left["settings_sha256"] == right["settings_sha256"],
                    "same_recorded_exposure": Decimal(left["recorded_exposure_usd"])
                    == Decimal(right["recorded_exposure_usd"]),
                    "physical_requests_left": left["physical_requests_by_category"],
                    "physical_requests_right": right["physical_requests_by_category"],
                    "cost_left": left["actual_total_cost_usd"],
                    "cost_right": right["actual_total_cost_usd"],
                    "interpretation": (
                        "paired diagnostics only; unequal or incomplete exposure is disclosed"
                    ),
                }
            )
    real = [r for r in results if r["origin"] != "fixture"]
    untested = ["model selection value (requires paired identical stage inputs)"]
    if not any(
        o.origin == "authorized_live"
        and bool(o.candidates)
        and any(a.category == "search" and a.outcome == "success" for a in o.attempts)
        for o in benchmark.observations
    ):
        untested.append("current live rankings")
    if not any(r["capture_judgments_known"] for r in real):
        untested.append("readable full-text yield")
    if not any(r["judged_final_statements"] for r in real):
        untested.append("interpretation/entailment quality")
    if not any(r["admission_utility_status"] == "evaluated" for r in real):
        untested.append("end-to-end admission utility")
    return {
        "schema_version": "research-quality-report-v1",
        "manifest_sha256": hashlib.sha256(raw).hexdigest(),
        "comparison_k": k,
        "new_paid_calls": 0,
        "observations": results,
        "comparisons": comparisons,
        "origins": dict(Counter(o.origin for o in benchmark.observations)),
        "pending_reference_topics": [
            t.topic_id for t in benchmark.topics if t.reference.status == "pending"
        ],
        "quality_established": (
            "fixture arithmetic or frozen observations only; no general live-quality claim"
        ),
        "untested": untested,
    }


def summary(report: dict[str, Any]) -> str:
    lines = [
        "# Research quality benchmark",
        "",
        f"Manifest: `{report['manifest_sha256']}`",
        f"Comparison K: {report['comparison_k']}; new paid calls: 0.",
        "",
        "Origins: " + json.dumps(report["origins"], sort_keys=True),
        "",
        "Every score is attributed to its observation origin. Unknown is not zero.",
        "",
    ]
    for observation in report["observations"]:
        lines.extend(
            [
                f"## {observation['observation_id']} ({observation['origin']})",
                "",
                "```json",
                json.dumps(observation, indent=2, sort_keys=True),
                "```",
                "",
            ]
        )
    lines.extend(
        [
            "Pending reference topics: " + ", ".join(report["pending_reference_topics"]),
            "",
            "Untested live claims: " + ", ".join(report["untested"]),
            "",
        ]
    )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--k", type=int, default=10)
    parser.add_argument("--replay", action="store_true")
    args = parser.parse_args(argv)
    try:
        report = evaluate(args.manifest, k=args.k, replay=args.replay)
    except (ValueError, OSError) as exc:
        # Validation errors may contain input data; do not echo raw private payloads.
        print(f"Benchmark failed validation ({type(exc).__name__}); no network calls executed.")
        return 2
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "results.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n"
    )
    (args.output_dir / "summary.md").write_text(summary(report))
    print(f"PASS: {len(report['observations'])} observations; new paid calls: 0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
