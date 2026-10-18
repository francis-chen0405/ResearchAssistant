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
