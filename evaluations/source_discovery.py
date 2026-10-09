"""Synthetic offline evaluation kept separate from historical evaluation semantics."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Literal
from uuid import UUID, uuid5

from pydantic import BaseModel, ConfigDict, Field, model_validator

from researchassistant.contracts.discovery_v2 import (
    V2ConceptGroup,
    V2ConceptualQuery,
    V2ProductDiscoveryPolicy,
    discovery_id,
    normalize_doi,
)
from researchassistant.contracts.model_contracts import DiscoveryProvider
from researchassistant.contracts.model_research import DiscoveryProvenance, NormalizedDiscoveryItem
from researchassistant.contracts.research_directions import ResearchDirection
from researchassistant.research.metadata_ranking import rank_metadata
from researchassistant.research.query_compiler import compile_query

_NAMESPACE = UUID("10000000-0000-4000-8000-000000000006")
DEFAULT_MANIFEST = Path(__file__).resolve().parent / "cases" / "source_discovery" / "manifest.json"


class FixtureWork(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    work_id: str = Field(min_length=1, max_length=80, pattern=r"^[a-z0-9-]+$")
    title: str = Field(min_length=1, max_length=300)
    doi: str | None = None
    provider_rank: int = Field(ge=1, le=100)
    publication_type: Literal["article", "report", "blog", "engineering"] = "article"
    abstract: str = ""
    document: str = ""
    preview_annotated: bool = False
    preview_relevance_terms: tuple[str, ...] = ()
    disposition: Literal["usable", "shell", "unavailable"] = "usable"
    independence: Literal["independent", "same_work", "unresolved"] = "independent"
    finding: Literal["supports", "challenges", "mixed", "unclear"] = "unclear"
    seed_id: str | None = None
    expected_rationale: str | None = Field(default=None, max_length=500)


class FixtureEdge(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    source: str
    target: str
    relationship: Literal["references", "citing", "related"]


class Scenario(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    scenario_id: str = Field(pattern=r"^[a-z0-9-]+$")
    topic: Literal["alpr-crime", "alpr-discrimination", "biomedical", "non-scholarly"]
    claim: str = Field(min_length=8, max_length=500)
    concepts: tuple[str, ...] = Field(min_length=1, max_length=5)
    aliases: tuple[str, ...] = Field(default=(), max_length=3)
    baseline_work_ids: tuple[str, ...] = Field(min_length=5, max_length=5)
    provider_specific_top5_ids: tuple[str, ...] = Field(min_length=5, max_length=5)
    product_query_work_ids: tuple[str, ...] = Field(min_length=5, max_length=40)
    expected_work_ids: tuple[str, ...] = Field(min_length=1, max_length=12)
    works: tuple[FixtureWork, ...] = Field(min_length=5, max_length=40)
    edges: tuple[FixtureEdge, ...] = ()
    provider_enabled: bool = True
    requested_depth: int = Field(default=20, ge=1, le=50)
    acquisition_k: int = Field(default=18, ge=1, le=20)
    model_calls: int | None = None
    model_tokens: int | None = None
    cost_usd: str | None = None
    seed_expansion_enabled: bool = True

    @model_validator(mode="after")
    def relationships_are_closed(self) -> Scenario:
        ids = [work.work_id for work in self.works]
        if len(ids) != len(set(ids)):
            raise ValueError("work IDs must be unique; publication versions share a DOI")
        if not set(self.expected_work_ids) <= set(ids):
            raise ValueError("every expected work must occur in fixture results")
        work_by_id = {work.work_id: work for work in self.works}
        if any(not work_by_id[work_id].expected_rationale for work_id in self.expected_work_ids):
            raise ValueError("every expected work requires an independent fixture rationale")
        response_ids = (
            *self.baseline_work_ids,
            *self.provider_specific_top5_ids,
            *self.product_query_work_ids,
        )
        if not set(response_ids) <= set(ids):
            raise ValueError("frozen query responses must refer only to manifest works")
        if any(edge.source not in ids or edge.target not in ids for edge in self.edges):
            raise ValueError("graph edges must refer to fixture works")
        if any(work.preview_annotated and not work.preview_relevance_terms for work in self.works):
            raise ValueError("annotated preview cases require manual relevance terms")
        return self


class Manifest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    manifest_version: Literal["source-discovery-evaluation-v1"]
    provenance: Literal["author-created synthetic metadata and documents"]
    live_quality_claim: Literal[False] = False
    scenarios: tuple[Scenario, ...] = Field(min_length=4, max_length=20)

    @model_validator(mode="after")
    def topic_coverage(self) -> Manifest:
        required = {"alpr-crime", "alpr-discrimination", "biomedical", "non-scholarly"}
        if not required <= {scenario.topic for scenario in self.scenarios}:
            raise ValueError("manifest must cover all four required topic classes")
        return self


class ScenarioResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    scenario_id: str
    expected: int
    baseline5_recall: float
    new_recall: float
    acquired_usable_recall: float
    baseline5_precision: float
    new_precision: float
    acquired_usable_precision: float
    seed_only_discoveries: tuple[str, ...]
    duplication_rate: float
    useful_preview_coverage: float
    preview_exactness: float
    preview_relevance: float
    physical_requests: int | None
    seed_physical_requests: int
    acquisition_scrape_attempts: int
    metadata_fixture_requests: int
    request_budget_bound: int
    physical_request_cost_usd: str | None
    reserved_provider_cost_usd: str | None
    seed_action_status: str | None
    seed_dispositions: dict[str, int]
    model_calls: int | None
    model_tokens: int | None
    shortlisted: tuple[str, ...]
    acquired_usable: tuple[str, ...]
    dispositions: dict[str, int]
    admission_status: Literal["not_assessed"]
    unresolved_independence_abstentions: int
    budget_compliant: bool
    ablations: dict[str, float | None]
    counterexamples: tuple[str, ...]


class EvaluationReport(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    manifest_sha256: str
    synthetic_only: Literal[True] = True
    scenarios: tuple[ScenarioResult, ...]
    aggregate: dict[str, float]
    limitations: tuple[str, ...]


def _uuid(key: str) -> UUID:
    return uuid5(_NAMESPACE, key)


def _work_key(work: FixtureWork) -> str:
    """Publication aliases with an exact DOI represent one expected work."""
    return f"doi:{normalize_doi(work.doi)}" if work.doi else f"fixture:{work.work_id}"


def _item(scenario: Scenario, work: FixtureWork, run_id: UUID) -> NormalizedDiscoveryItem:
    item_id = _uuid(f"{scenario.scenario_id}/{work.work_id}")
    query_id = _uuid(f"{scenario.scenario_id}/query")
    url = f"https://fixture.invalid/{scenario.scenario_id}/{work.work_id}"
    provenance = DiscoveryProvenance(
        provider=DiscoveryProvider.OPENALEX,
        query_id=query_id,
        query_text=" ".join(scenario.concepts),
        direction=ResearchDirection.SUPPORT,
        round_number=1,
        provider_rank=work.provider_rank,
        original_url=url,
    )
    return NormalizedDiscoveryItem(
        run_id=run_id,
        item_id=item_id,
        provider=DiscoveryProvider.OPENALEX,
        query_id=query_id,
        query_text=" ".join(scenario.concepts),
        direction=ResearchDirection.SUPPORT,
        round_number=1,
        provider_rank=work.provider_rank,
        source_url=url,
        canonical_url=url,
        title=work.title,
        abstract=work.abstract,
        doi=work.doi,
        authors=("Synthetic author",),
        publication_date="2024-01-01",
        source_type=work.publication_type,
        provenance_chain=(provenance,),
        discovered_at="2026-10-08T00:00:00Z",
    )


def evaluate_manifest(path: Path = DEFAULT_MANIFEST) -> EvaluationReport:
    raw = path.read_bytes()
    manifest = Manifest.model_validate_json(raw)
    results: list[ScenarioResult] = []
    baseline_recall: list[float] = []
    new_recall: list[float] = []
    for scenario in manifest.scenarios:
        run_id = _uuid(f"run/{scenario.scenario_id}")
        policy = V2ProductDiscoveryPolicy(
            metadata_depth=min(20, scenario.requested_depth),
            sources_per_direction_per_round=20,
            seed_expansion_enabled=scenario.seed_expansion_enabled,
            scholarly_search_mode="lexical",
        )
        conceptual = V2ConceptualQuery(
            run_id=run_id,
            artifact_id=discovery_id(run_id, "V2ConceptualQuery", "query/broad"),
            identity_key="query/broad",
            required_concepts=(
                V2ConceptGroup(concept=scenario.concepts[0], synonyms=scenario.aliases),
                *(V2ConceptGroup(concept=term) for term in scenario.concepts[1:]),
            ),
            purpose="broad",
            direction=ResearchDirection.SUPPORT,
            provider=DiscoveryProvider.OPENALEX,
            round_number=1,
        )
        compiled = (
            compile_query(conceptual, requested_depth=scenario.requested_depth, policy=policy)
            if scenario.provider_enabled
            else None
        )
        query_map = {work.work_id: work for work in scenario.works}
        work_index = {work.work_id: index for index, work in enumerate(scenario.works, 1)}
        work_by_provider_id = {
            f"https://openalex.org/W{work_index[work.work_id]}": work for work in scenario.works
        }
        query_works = tuple(
            query_map[work_id]
            for work_id in (
                scenario.product_query_work_ids[: compiled.effective_depth]
                if compiled is not None
                else ()
            )
        )
        seed_result = None
        expanded_works: tuple[FixtureWork, ...] = ()
        if scenario.provider_enabled and scenario.seed_expansion_enabled:
            from evaluations.source_discovery_transport import (
                SeedFixtureWork,
                run_seed_expansion_fixture,
            )

            seed_manifest = tuple(
                SeedFixtureWork(
                    work_id=work.work_id,
                    openalex_id=f"W{work_index[work.work_id]}",
                    doi=work.doi,
                    title=work.title,
                    abstract=work.abstract,
                    year=2024,
                    document=work.document,
                    acquisition_outcome=work.disposition,
                )
                for work in scenario.works
            )
            seed_by_id = {work.work_id: work for work in seed_manifest}
            seed_source = next((work for work in scenario.works if work.seed_id), None)
            if seed_source is not None:
                targets = tuple(
                    edge.target
                    for edge in scenario.edges
                    if edge.source == seed_source.work_id and edge.target != seed_source.work_id
                )
                seed_result = run_seed_expansion_fixture(
                    scenario_id=scenario.scenario_id,
                    claim=scenario.claim,
                    seed=seed_by_id[seed_source.work_id],
                    works=seed_manifest,
                    neighbor_work_ids=targets,
                    max_neighbors=min(10, policy.max_neighbors_per_seed),
                    run_id=run_id,
                )
                expanded_ids = {work.work_id for work in seed_result.neighbors}
                expanded_works = tuple(
                    work for work in scenario.works if work.work_id in expanded_ids
                )
        query_items = tuple(_item(scenario, work, run_id) for work in query_works)
        expanded_items = seed_result.graph_items if seed_result is not None else ()
        items = (*query_items, *expanded_items)
        by_item = {item.item_id: item for item in items}
        rank_rows = rank_metadata(items, exact_claim=scenario.claim, policy=policy)
        query_rank_rows = rank_metadata(query_items, exact_claim=scenario.claim, policy=policy)
        rank_items = [by_item[row.item_id] for row in rank_rows]
        work_by_item = {
            item.item_id: work for item, work in zip(query_items, query_works, strict=True)
        }
        for item in expanded_items:
            provider_ids = [
                json.loads(entry.value_json)
                for entry in item.provider_metadata
                if entry.key == "external_id"
            ]
            if (
                len(provider_ids) != 1
                or not isinstance(provider_ids[0], str)
                or provider_ids[0] not in work_by_provider_id
            ):
                raise ValueError("graph candidate lacks one exact manifest provider identity")
            work_by_item[item.item_id] = work_by_provider_id[provider_ids[0]]
        if len(work_by_item) != len(items):
            raise ValueError("production graph candidates must map back to one frozen work")
        rank_by_item = {row.item_id: row for row in rank_rows}
        expected = {_work_key(query_map[work_id]) for work_id in scenario.expected_work_ids}

        def found(
            works: list[FixtureWork] | tuple[FixtureWork, ...],
            expected_keys: frozenset[str] = frozenset(expected),
        ) -> set[str]:
            return {_work_key(work) for work in works} & expected_keys

        baseline = tuple(query_map[work_id] for work_id in scenario.baseline_work_ids)
        baseline_found = found(baseline)
        # Deduplicate DOI versions after the production ranker, preserving its best record.
        unique_ranked: list[FixtureWork] = []
        seen: set[str] = set()
        for item in rank_items:
            key = rank_by_item[item.item_id].work_key
            if key not in seen:
                unique_ranked.append(work_by_item[item.item_id])
                seen.add(key)
        shortlist = unique_ranked[
            : min(
                scenario.acquisition_k,
                policy.sources_per_direction_per_round,
                policy.max_acquisition_per_round,
            )
        ]
        query_discovered = {work.work_id for work in query_works}
        seed_only = tuple(
            sorted(work.work_id for work in expanded_works if work.work_id not in query_discovered)
        )
        if not scenario.provider_enabled:
            shortlist = []
        from evaluations.source_discovery_transport import (
            SeedFixtureWork,
            run_acquisition_fixture,
        )

        graph_url_by_work = {
            work_by_item[item.item_id].work_id: item.source_url for item in expanded_items
        }
        acquisition = run_acquisition_fixture(
            scenario.scenario_id,
            scenario.claim,
            tuple(
                SeedFixtureWork(
                    work_id=work.work_id,
                    openalex_id=f"W{work_index[work.work_id]}",
                    doi=work.doi,
                    title=work.title,
                    abstract=work.abstract,
                    year=2024,
                    document=work.document,
                    acquisition_outcome=work.disposition,
                    source_url=graph_url_by_work.get(work.work_id),
                )
                for work in shortlist
            ),
        )
        acquired = acquisition.usable_work_ids
        previews_by_work = {preview.work_id: preview for preview in acquisition.previews}
        preview_values = []
        for preview in acquisition.previews:
            work = query_map[preview.work_id]
            if not work.preview_annotated:
                continue
            spans = preview.preview.spans
            exact = all(preview.snapshot_text[span.start : span.end] == span.text for span in spans)
            relevant = bool(spans) and all(
                any(
                    term.casefold() in span.text.casefold() for term in work.preview_relevance_terms
                )
                for span in spans
            )
            useful = bool(spans) and preview.preview.capture_usable
            preview_values.append((useful, exact, relevant))
        original_rank = {work.work_id: index for index, work in enumerate(shortlist)}
        # Both selection arms see the same actual usable-snapshot pool. Acquisition failures
        # affect acquired recall above; they do not enter the preview ranking comparison.
        preview_candidates = [work for work in shortlist if work.work_id in acquired]
        eligible_previews = sorted(preview_candidates, key=lambda work: original_rank[work.work_id])
        selected_at_12 = sorted(
            eligible_previews,
            key=lambda work: (
                not previews_by_work[work.work_id].preview.capture_usable,
                original_rank[work.work_id],
            ),
        )[:12]
        seed_found = found(shortlist)
        baseline_value = len(baseline_found) / len(expected)
        new_value = len(seed_found) / len(expected)
        resolved_shortlist = [work for work in shortlist if work.independence != "unresolved"]
        resolved_baseline = [work for work in baseline if work.independence != "unresolved"]
        base_precision = len(found(resolved_baseline)) / max(
            1, len({_work_key(work) for work in resolved_baseline})
        )
        resolved_acquired = [work for work in resolved_shortlist if work.work_id in acquired]
        new_precision = len(found(resolved_shortlist)) / max(
            1, len({_work_key(work) for work in resolved_shortlist})
        )
        acquired_recall = len(found([query_map[work_id] for work_id in acquired])) / len(expected)
        acquired_precision = len(found(resolved_acquired)) / max(
            1, len({_work_key(work) for work in resolved_acquired})
        )
        duplicate_count = len(query_works) - len({row.work_key for row in query_rank_rows})
        query_work_by_item = {
            item.item_id: work for item, work in zip(query_items, query_works, strict=True)
        }
        query_unique: list[FixtureWork] = []
        query_seen: set[str] = set()
        for row in query_rank_rows:
            if row.work_key not in query_seen:
                query_seen.add(row.work_key)
                query_unique.append(query_work_by_item[row.item_id])
        seed_requests = seed_result.physical_requests if seed_result is not None else 0
        acquisition_requests = acquisition.physical_scrape_attempts
        physical_requests = seed_requests + acquisition_requests
        reserved_cost = seed_result.reserved_cost_usd if seed_result is not None else None
        product_top5 = (
            found([query_map[work_id] for work_id in scenario.provider_specific_top5_ids])
            if compiled is not None
            else set()
        )
        ablations = {
            "provider_specific_query_at_5": len(product_top5) / len(expected),
            "deeper_retrieval_and_ranking": len(found(query_unique[: scenario.acquisition_k]))
            / len(expected),
            "preview_aware_selection_at_12": len(found(selected_at_12)) / len(expected),
            "rank_only_selection_at_12": len(found(eligible_previews[:12])) / len(expected),
            "seed_expansion": new_value,
        }
        counterexamples = []
        if new_value < 1:
            counterexamples.append("at least one curated expected work was not shortlisted")
        if any(value != "usable" for value in acquisition.dispositions.values()):
            counterexamples.append(
                "actual acquisition found shortlisted sources that were unusable"
            )
        if acquired_recall < new_value:
            counterexamples.append(
                "usable full text reduced expected-work recall after acquisition"
            )
        result = ScenarioResult(
            scenario_id=scenario.scenario_id,
            expected=len(expected),
            baseline5_recall=baseline_value,
            new_recall=new_value,
            acquired_usable_recall=acquired_recall,
            baseline5_precision=base_precision,
            new_precision=new_precision,
            acquired_usable_precision=acquired_precision,
            seed_only_discoveries=seed_only,
            duplication_rate=duplicate_count / max(1, len(query_works)),
            useful_preview_coverage=sum(int(row[0]) for row in preview_values)
            / max(1, len(preview_values)),
            preview_exactness=sum(int(row[1]) for row in preview_values)
            / max(1, len(preview_values)),
            preview_relevance=sum(int(row[2]) for row in preview_values)
            / max(1, len(preview_values)),
            physical_requests=physical_requests,
            seed_physical_requests=seed_requests,
            acquisition_scrape_attempts=acquisition_requests,
            metadata_fixture_requests=0,
            request_budget_bound=((3 if seed_result is not None else 0) + len(shortlist)),
            physical_request_cost_usd=None,
            reserved_provider_cost_usd=reserved_cost,
            seed_action_status=seed_result.action_status if seed_result is not None else None,
            seed_dispositions=seed_result.dispositions if seed_result is not None else {},
            model_calls=0,
            model_tokens=0,
            shortlisted=tuple(work.work_id for work in shortlist),
            acquired_usable=tuple(acquired),
            dispositions=dict(sorted(Counter(acquisition.dispositions.values()).items())),
            admission_status="not_assessed",
            unresolved_independence_abstentions=sum(
                work.independence == "unresolved" for work in shortlist
            ),
            budget_compliant=seed_requests <= 3
            and acquisition_requests <= 25
            and len(shortlist) <= 25
            and scenario.model_calls in (None, 0)
            and scenario.model_tokens in (None, 0),
            ablations=ablations,
            counterexamples=tuple(counterexamples),
        )
        # Compiler output must faithfully carry the requested depth into its bounded action.
        if compiled is not None and compiled.requested_depth != scenario.requested_depth:
            raise ValueError("compiler did not preserve requested depth")
        results.append(result)
        baseline_recall.append(baseline_value)
        new_recall.append(new_value)
    return EvaluationReport(
        manifest_sha256=hashlib.sha256(raw).hexdigest(),
        scenarios=tuple(results),
        aggregate={
            "baseline5_recall": sum(baseline_recall) / len(baseline_recall),
            "new_recall": sum(new_recall) / len(new_recall),
            "recall_delta": sum(new_recall) / len(new_recall)
            - sum(baseline_recall) / len(baseline_recall),
        },
        limitations=(
            "All records, metadata responses, graph edges, and documents are author-created; "
            "reported recall and precision are fixture metrics, not live-provider or real-world "
            "quality evidence.",
            "The production compiler and ranker replay frozen synthetic metadata responses. "
            "Provider search ranking and network transport for the metadata query are not modeled.",
            "Graph expansion executes the production offer/execute path through an offline fake "
            "OpenAlex transport; acquisition and claim previews execute run_v2_acquisition_probe "
            "through a deterministic fake scraper. Counts include only those fake seed and scrape "
            "requests; their combined monetary cost is unknown. The reported reserved amount is "
            "seed-action exposure only.",
            "Preview relevance is scored only for fixture-annotated spans among shortlisted works. "
            "Rank-only and capture-aware 12-item selection use the same actually usable snapshot "
            "pool; acquisition failures are measured separately. Capture usability sorts the "
            "preview arm, with frozen rank as a tie-break. This synthetic rule is not evidence of "
            "user value.",
            "The runner does not execute Analyst review or evidence admission; admission remains "
            "not assessed. No model stage runs, so model calls and tokens are zero.",
        ),
    )


def render_report(report: EvaluationReport) -> str:
    lines = [
        "# Offline source-discovery evaluation",
        "",
        f"Manifest SHA-256: {report.manifest_sha256}",
        "Synthetic fixture evidence only; no live-quality claim.",
        "",
        "| Scenario | Expected | Baseline 5 recall / precision | New recall / precision | "
        "Seed-only | Duplicate rate | Useful / exact / relevant previews | "
        "Fake requests / total cost (seed reserved) | "
        "Usable after shortlist (recall / precision) |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in report.scenarios:
        cost = "unknown" if row.physical_request_cost_usd is None else row.physical_request_cost_usd
        reserved = row.reserved_provider_cost_usd or "unknown"
        request_count = "unknown" if row.physical_requests is None else str(row.physical_requests)
        lines.append(
            f"| {row.scenario_id} | {row.expected} | "
            f"{row.baseline5_recall:.3f} / {row.baseline5_precision:.3f} | "
            f"{row.new_recall:.3f} / {row.new_precision:.3f} | {len(row.seed_only_discoveries)} | "
            f"{row.duplication_rate:.3f} | {row.useful_preview_coverage:.3f} / "
            f"{row.preview_exactness:.3f} / {row.preview_relevance:.3f} | "
            f"{request_count} / {cost} (reserved {reserved}) | "
            f"{len(row.acquired_usable)}/{len(row.shortlisted)} "
            f"({row.acquired_usable_recall:.3f} / {row.acquired_usable_precision:.3f}) |"
        )
    lines.extend(["", "## Ablations", ""])
    for row in report.scenarios:
        lines.append(f"- {row.scenario_id}: {json.dumps(row.ablations, sort_keys=True)}")
    lines.extend(["", "## Limitations", "", *(f"- {item}" for item in report.limitations), ""])
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the synthetic source-discovery evaluation.")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--json-output", type=Path)
    parser.add_argument("--summary-output", type=Path)
    args = parser.parse_args(argv)
    try:
        report = evaluate_manifest(args.manifest)
        machine = json.dumps(report.model_dump(mode="json"), indent=2, sort_keys=True) + "\n"
        summary = render_report(report)
        if args.json_output:
            args.json_output.parent.mkdir(parents=True, exist_ok=True)
            args.json_output.write_text(machine, encoding="utf-8")
        if args.summary_output:
            args.summary_output.parent.mkdir(parents=True, exist_ok=True)
            args.summary_output.write_text(summary, encoding="utf-8")
        if not args.json_output and not args.summary_output:
            print(summary)
        return 0 if all(row.budget_compliant for row in report.scenarios) else 1
    except (OSError, ValueError, TypeError) as exc:
        print(f"source-discovery evaluation failed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
