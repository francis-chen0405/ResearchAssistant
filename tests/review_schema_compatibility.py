"""Verify only approved versioned additions before comparing historical schema hashes."""

from __future__ import annotations

from typing import Any


def normalize_approved_additive_fields(
    document: dict[str, Any], *, reference_root: str = "$defs"
) -> None:
    """Verify and remove approved additive fields from a frozen schema snapshot.

    ``reference_root`` differs between Pydantic model schemas (``$defs``) and
    FastAPI's OpenAPI components (``components/schemas``). Assertions happen
    before removal so an unrelated schema change cannot be normalized away.
    """
    confirmed_location = {
        "additionalProperties": False,
        "properties": {
            "basis": {
                "enum": ["metadata", "publisher_url", "pmc_header"],
                "title": "Basis",
                "type": "string",
            },
            "direction": {"$ref": f"#/{reference_root}/ResearchDirection"},
            "doi": {"title": "Doi", "type": "string"},
            "research_round": {
                "maximum": 4,
                "minimum": 1,
                "title": "Research Round",
                "type": "integer",
            },
            "snapshot_hash": {
                "pattern": "^[0-9a-f]{64}$",
                "title": "Snapshot Hash",
                "type": "string",
            },
            "snapshot_id": {"format": "uuid", "title": "Snapshot Id", "type": "string"},
            "source_id": {"format": "uuid", "title": "Source Id", "type": "string"},
            "source_url": {"title": "Source Url", "type": "string"},
        },
        "required": [
            "source_id",
            "snapshot_id",
            "snapshot_hash",
            "source_url",
            "research_round",
            "direction",
            "doi",
            "basis",
        ],
        "title": "ConfirmedPaperLocation",
        "type": "object",
    }

    def ref(name: str) -> dict[str, str]:
        return {"$ref": f"#/{reference_root}/{name}"}

    def optional_nonnegative(title: str) -> dict[str, Any]:
        return {
            "anyOf": [{"minimum": 0, "type": "integer"}, {"type": "null"}],
            "default": None,
            "title": title,
        }

    bounded_urls = {
        "default": [],
        "items": {"type": "string"},
        "maxItems": 240,
        "title": "Alternate Source Urls",
        "type": "array",
    }
    bounded_locations = {
        "default": [],
        "items": ref("ConfirmedPaperLocation"),
        "maxItems": 240,
        "title": "Paper Locations",
        "type": "array",
    }
    models = (document, *document.get("$defs", {}).values())
    # OpenAPI's component schemas are passed as a mapping, rather than a model
    # schema with a $defs object.
    if "$defs" not in document and all(isinstance(value, dict) for value in document.values()):
        models = tuple(document.values())
    for model in models:
        properties = model.get("properties", {})
        title = model.get("title")
        if title == "V2SourceSelectionInput":
            assert properties.pop("model_view_policy") == {
                "anyOf": [
                    {"const": "compact-selection-v1", "type": "string"},
                    {"type": "null"},
                ],
                "default": None,
                "title": "Model View Policy",
            }
        elif title in {"V2SourceSelectionCandidate", "V2ResultSource"}:
            assert properties.pop("alternate_source_urls") == bounded_urls
        elif title == "V2MergedSurvivor":
            assert properties.pop("paper_locations") == bounded_locations
        elif title == "V2ProviderRunDiagnostics":
            assert properties.pop("blocked_queries") == optional_nonnegative("Blocked Queries")
            assert properties.pop("unknown_queries") == optional_nonnegative("Unknown Queries")

    definitions = document.get("$defs")
    if definitions is not None and "ConfirmedPaperLocation" in definitions:
        assert definitions.pop("ConfirmedPaperLocation") == confirmed_location
    elif "$defs" not in document and "ConfirmedPaperLocation" in document:
        assert document.pop("ConfirmedPaperLocation") == confirmed_location


def verify_review_schema_additions(document: dict[str, Any]) -> None:
    normalize_approved_additive_fields(document)
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
        if title in {"RetrievalRecord", "ProvisionalCandidate", "CandidateQuoteBlock"}:
            assert properties["search_rank"]["maximum"] == 100
            properties["search_rank"]["maximum"] = 25
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
            assert properties.pop("assessed_source_findings") == {
                "default": [],
                "items": {"$ref": "#/$defs/AssessedSourceFinding"},
                "maxItems": 4,
                "title": "Assessed Source Findings",
                "type": "array",
            }
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
        elif title == "V2InitialPlannerInput":
            assert properties.pop("saved_source_leads") == {
                "default": [],
                "items": {"$ref": "#/$defs/SavedSourceLead"},
                "maxItems": 12,
                "title": "Saved Source Leads",
                "type": "array",
            }
    for name in ("AssessedSourceFinding", "SavedSourceLead"):
        document.get("$defs", {}).pop(name, None)
