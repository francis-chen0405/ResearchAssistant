"""Offline production-contract fixtures for publication grouping and new exports."""

from pathlib import Path
from uuid import uuid4

import pytest
import test_v2_phase9_luna_evidence_analyst as fixture
from test_v2_phase10_reviewer_ledger import Phase10Provider, _approved
from test_v2_phase11_final_output import _continuation, _synthesis

from researchassistant.agents.v2_evidence_analyst import run_v2_evidence_analyst
from researchassistant.agents.v2_final_output import (
    V2_FINAL_OUTPUT_ARTIFACT_KEY,
    build_v2_final_research_output,
)
from researchassistant.agents.v2_reviewer_ledger import run_v2_reviewer_ledger
from researchassistant.agents.v2_source_selection import calculate_v2_deep_analysis_queue
from researchassistant.api.application_services.result_reads import read_evidence
from researchassistant.common.utils import derive_quote_block_id
from researchassistant.contracts.models import V2EvidenceAnalystBatchInput, V2FinalResearchOutput
from researchassistant.evidence.brief_export import BriefExportFormat, export_released_brief
from researchassistant.evidence.report_review import build_publication_opening
from researchassistant.storage.store import insert_v2_artifact


def production_report(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[str, V2FinalResearchOutput]:
    """Two study designs and a duplicate copy pass the real Analyst/Reviewer pipeline."""
    run_id = uuid4()
    path = fixture._prepare_db(tmp_path, run_id)
    studies = [
        ("REG-2024", "randomized", "mobile tutoring", "course completion", "supports"),
        ("REG-2025", "observational", "fixed classrooms", "exam scores", "challenges"),
        ("REG-2024", "randomized", "mobile tutoring", "course completion", "supports"),
    ]
    batches, assessments, statements = [], [], []
    for index, (registry, design, intervention, outcome, relationship) in enumerate(studies):
        statement = (
            f"The {design} study {registry} measured {outcome} after {intervention} "
            "for six months among participating adults enrolled in the regional education "
            "program, with course completion recorded only for participants who remained "
            "in the study."
        )
        with monkeypatch.context() as patch:
            patch.setattr(fixture, "QUOTE", statement)
            patch.setattr(
                fixture, "SNAPSHOT_TEXT", statement + " The follow-up was limited to six months."
            )
            batch = fixture._batch_input(run_id)
        survivor = batch.queue_result.input.survivors[0].model_copy(
            update={
                "source_type": "randomized trial"
                if design == "randomized"
                else "observational study"
            }
        )
        selection_input = batch.queue_result.input.model_copy(update={"survivors": (survivor,)})
        batch = batch.model_copy(
            update={
                "queue_result": batch.queue_result.model_copy(update={"input": selection_input})
            }
        )
        # Location changes propagate through every candidate/snapshot reference.
        batch = V2EvidenceAnalystBatchInput.model_validate_json(
            batch.model_dump_json().replace(
                "https://example.test/regional-evaluation", f"https://mirror{index}.example/report"
            )
        )
        queued = batch.queued_candidates[0]
        candidate = queued.candidate
        candidate = candidate.model_copy(
            update={
                "quote_block_id": derive_quote_block_id(
                    candidate.source_url, candidate.snapshot_sha256, list(candidate.segment_offsets)
                )
            }
        )
        batch = batch.model_copy(
            update={"queued_candidates": (queued.model_copy(update={"candidate": candidate}),)}
        )
        batches.append(batch)
        assessments.append(
            fixture._assessment().model_copy(
                update={
                    "narrowest_supported_proposition": statement,
                    "canonical_factual_statement": statement,
                    "relationship_to_claim": type(fixture._assessment().relationship_to_claim)(
                        relationship
                    ),
                    "material_limitations": ("The follow-up was limited to six months.",),
                    "inferential_boundaries": (),
                }
            )
        )
        statements.append(statement)
    queue = batches[0].queue_result
    survivors = tuple(batch.queue_result.input.survivors[0] for batch in batches)
    selection = queue.input.model_copy(update={"survivors": survivors})
    ordered = tuple(source.source_id for source in survivors)
    recommendations = tuple(batch.queue_result.recommendation_rationales[0] for batch in batches)
    plan = calculate_v2_deep_analysis_queue(
        selection_input=selection,
        ordered_source_ids=ordered,
        recommended_source_ids=ordered,
        recommendation_rationales=recommendations,
        routing_config=fixture._routing(),
        budget=queue.initial_budget,
    )
    queue = queue.model_copy(
        update={
            "input": selection,
            "recommended_source_ids": ordered,
            "recommendation_rationales": recommendations,
            **{key: getattr(plan, key) for key in type(queue).model_fields if hasattr(plan, key)},
        }
    )
    batch = batches[0].model_copy(
        update={
            "queue_result": queue,
            "queued_candidates": tuple(batch.queued_candidates[0] for batch in batches),
        }
    )
    batch = V2EvidenceAnalystBatchInput.model_validate_json(batch.model_dump_json())
    responses = assessments
    analyst = run_v2_evidence_analyst(
        db_path=path,
        batch_input=batch,
        llm_provider=fixture.FakeLunaAnalyst(responses),
        routing_config=fixture._routing(),
        clock=lambda: fixture.NOW,
    )
    reviewed = run_v2_reviewer_ledger(
        db_path=path,
        analyst_result=analyst,
        llm_provider=Phase10Provider([_approved() for _ in studies]),
        routing_config=fixture._routing(),
        clock=lambda: fixture.NOW,
    )
    assert all(source.ledger_record is not None for source in reviewed.source_results), (
        reviewed.model_dump_json(indent=2)
    )
    synthesis = _synthesis(reviewed)
    from agents.synthesizer import _item_from_ledger

    section = synthesis.sections[0].model_copy(
        update={
            "items": tuple(
                _item_from_ledger(source.ledger_record) for source in reviewed.source_results
            )
        }
    )
    synthesis = synthesis.model_copy(update={"sections": (section,)})
    output = build_v2_final_research_output(
        reviewer_result=reviewed,
        continuation=_continuation(run_id),
        synthesis=synthesis,
        created_at=fixture.NOW,
    )
    assert output.release_validation.valid, output.release_validation.errors
    insert_v2_artifact(path, V2_FINAL_OUTPUT_ARTIFACT_KEY, output, fixture.NOW)
    return path, output


def test_production_projection_export_and_duplicate_publication_summary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path, output = production_report(tmp_path, monkeypatch)
    display = read_evidence(path, output.run_id)
    assert len(display.items) == 3
    assert "unknown" in " ".join(display.budget_context)
    from decimal import Decimal

    from researchassistant.providers.v2_budget import V2PhysicalCallCompletion, V2PhysicalCallStart

    for sequence in (1, 2):
        insert_v2_artifact(
            path,
            f"phase-13-physical-call-{sequence:03d}-start",
            V2PhysicalCallStart(
                run_id=output.run_id,
                sequence=sequence,
                stage="evidence_analyst",
                model_alias="fixture",
                reserved_tokens=100 * sequence,
                reserved_cost_usd=Decimal("0.01") * sequence,
                source_id=display.items[0].source_id,
                source_token_cap=1000,
                source_physical_call_cap=7,
                started_at=fixture.NOW,
            ),
            fixture.NOW,
        )
    insert_v2_artifact(
        path,
        "phase-13-physical-call-001-completion",
        V2PhysicalCallCompletion(
            run_id=output.run_id,
            sequence=1,
            succeeded=True,
            usage_tokens=50,
            usage_cost_usd=Decimal("0.005"),
            completed_at=fixture.NOW,
        ),
        fixture.NOW,
    )
    from hashlib import sha256

    from researchassistant.agents.v2_reviewer_ledger import V2_REVIEWER_LEDGER_ARTIFACT_KEY
    from researchassistant.contracts.models import V2ReviewerLedgerBatchResult
    from researchassistant.evidence.report_review import (
        PublicationReview,
        V2ReportStudyReview,
        record_review,
    )
    from researchassistant.storage.store import insert_snapshot, read_v2_artifact

    admission = V2ReviewerLedgerBatchResult.model_validate_json(
        read_v2_artifact(path, output.run_id, V2_REVIEWER_LEDGER_ARTIFACT_KEY).payload_json
    )
    template = admission.analyst_result.input.queued_candidates[0].snapshot
    from test_phase2 import _make_planner, _make_retrieval

    from researchassistant.storage.store import insert_planner_output, insert_retrieval_attempt

    planner = _make_planner(output.run_id)
    insert_planner_output(path, planner)
    publications = []
    for registry in ("REG-2024", "REG-2025"):
        text = f"{registry} Registered evaluation Ada Author 2024 Public Institute"
        retrieval = _make_retrieval(output.run_id, planner.search_queries[0].query_id)
        insert_retrieval_attempt(path, retrieval)
        authority = template.model_copy(
            update={
                "snapshot_id": uuid4(),
                "retrieval_attempt_id": retrieval.retrieval_attempt_id,
                "source_url": f"https://institute.example/{registry}",
                "normalized_text": text,
                "snapshot_sha256": sha256(text.encode()).hexdigest(),
                "word_count": len(text.split()),
            }
        )
        insert_snapshot(path, authority)
        publications.append(
            PublicationReview(
                source_ids=tuple(
                    item.source_id for item in display.items if registry in item.quote_passage
                ),
                identifier=registry,
                authority=authority,
                title="Registered evaluation",
                authors=("Ada Author",),
                date="2024",
                venue="Public Institute",
            )
        )
    record_review(
        path,
        display,
        V2ReportStudyReview(
            run_id=output.run_id,
            reviewer="Offline fixture reviewer",
            rationale="Verified registration identifiers against captured institute publications.",
            reviewed_at=fixture.NOW,
            publications=tuple(publications),
        ),
    )
    grouped = read_evidence(path, output.run_id)
    items = grouped.items
    budget = " ".join(grouped.budget_context)
    assert "Reported spend subtotal: USD 0.005" in budget
    import re

    pending = re.search(r"Pending reservations: USD ([0-9.]+); ([0-9]+) tokens", budget)
    assert pending and Decimal(pending[1]) == Decimal("0.02") and int(pending[2]) == 200
    assert "source allowance 1000 tokens and 7 calls; 2 calls dispatched" in budget
    assert "not final totals" in budget
    assert all(item.verified_publication.verification == "authority_identifier" for item in items)
    assert len(grouped.publication_opening) == 3
    assert len(grouped.publication_opening[0].ledger_claim_ids) == 2
    assert "randomized" in grouped.publication_opening[0].text
    assert "observational" in grouped.publication_opening[1].text
    assert "six months" in grouped.publication_opening[2].text
    for fmt, suffix in (
        (BriefExportFormat.MARKDOWN, ".md"),
        (BriefExportFormat.DOCX, ".docx"),
        (BriefExportFormat.PDF, ".pdf"),
    ):
        export_released_brief(path, str(output.run_id), tmp_path / ("report" + suffix), fmt)
    exported = (tmp_path / "report.md").read_text()
    assert grouped.reading_aid_markdown in exported
    assert "not necessarily representative" not in exported
    assert "https://institute.example/REG-2024" in exported
    for item in display.items:
        assert item.approved_factual_statement in exported
        assert item.quote_passage in exported
        assert all(limitation in exported for limitation in item.limitations)
    assert all(line in exported for line in grouped.budget_context)
    for change in (
        {"verified_publication": None},
        {"approved_factual_statement": "A different conflicting result."},
    ):
        changed = list(items)
        changed[2] = changed[2].model_copy(update=change)
        assert not build_publication_opening(
            display.model_copy(update={"items": tuple(changed)})
        ).publication_opening
