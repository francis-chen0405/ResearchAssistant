"""Verify only approved versioned additions before comparing historical schema hashes."""

from __future__ import annotations

from typing import Any


def verify_review_schema_additions(document: dict[str, Any]) -> None:
    for model in (document, *document.get("$defs", {}).values()):
        properties = model.get("properties", {})
        if model.get("title") == "V2SourceSelectionSearchProvenance":
            assert properties.pop("provenance_version") == {
                "default": 1,
                "enum": [1, 2],
                "title": "Provenance Version",
                "type": "integer",
            }
            assert properties.pop("direction") == {
                "anyOf": [{"$ref": "#/$defs/ResearchDirection"}, {"type": "null"}],
                "default": None,
            }
        if model.get("title") == "ScoutBatchAudit":
            assert properties["attempted_calls"]["minimum"] == 0
            properties["attempted_calls"]["minimum"] = 1
            assert properties.pop("recovery_policy") == {
                "anyOf": [
                    {"const": "partial-ranking-recovery-v1", "type": "string"},
                    {"type": "null"},
                ],
                "default": None,
                "title": "Recovery Policy",
            }


def normalize_current_product_capacity(document: dict[str, Any]) -> None:
    """Verify current product capacity deltas before comparing frozen old schemas."""
    for model in (document, *document.get("$defs", {}).values()):
        properties = model.get("properties", {})
        title = model.get("title")
        if title == "V2AcquisitionPolicy":
            assert properties["max_clusters"]["maximum"] == 60
            properties["max_clusters"]["maximum"] = 25
        elif title == "V2ProductDiscoveryPolicy":
            assert properties["max_acquisition_per_round"]["default"] == 60
            assert properties["max_acquisition_per_round"]["maximum"] == 60
            assert properties["sources_per_direction_per_round"]["enum"][-1] == 30
            properties["max_acquisition_per_round"].update(default=25, maximum=25)
            properties["sources_per_direction_per_round"]["enum"].pop()
        elif title == "V2GapAnalysisInput":
            for field in ("surviving_sources", "source_families"):
                assert properties[field]["maxItems"] == 180
                properties[field]["maxItems"] = 75
        elif title == "V2AcquisitionRankingAudit":
            for field in (
                "acquisition_shortlisted_clusters",
                "fetched_documents",
                "usable_survivors",
            ):
                assert properties[field]["maximum"] == 60
                properties[field]["maximum"] = 25
        elif title == "V2SourceSelectionInput":
            assert properties["survivors"]["maxItems"] == 240
            properties["survivors"]["maxItems"] = 100
        elif title in {"RetrievalRecord", "ProvisionalCandidate", "CandidateQuoteBlock"}:
            assert properties["search_rank"]["maximum"] == 100
            properties["search_rank"]["maximum"] = 25
