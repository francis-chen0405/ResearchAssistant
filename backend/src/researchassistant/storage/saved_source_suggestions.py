"""Bounded read-only metadata suggestions from earlier runs in the same database."""

from __future__ import annotations

import re
from pathlib import Path
from uuid import UUID

from researchassistant.contracts.artifact_keys import discovery_round_keys
from researchassistant.contracts.discovery_v2 import normalize_doi
from researchassistant.contracts.model_evidence import V2FinalResearchOutput
from researchassistant.contracts.research_discovery import V2DiscoveryScoutOutput
from researchassistant.contracts.source_recovery import SavedSourceLead
from researchassistant.providers.ranking import canonical_discovery_url
from researchassistant.storage.store import (
    open_read_only_store,
    read_snapshot_connection,
    read_v2_artifact,
)


def saved_source_suggestions(
    db_path: str | Path, run_id: UUID, claim: str
) -> tuple[SavedSourceLead, ...]:
    """Return related titles/URLs only; no old quotes, scores, or judgments enter a new run."""
    words = {
        x
        for x in re.findall(r"[a-z]{4,}", claim.lower())
        if x not in {"that", "with", "from", "into", "make", "increases"}
    }
    ranked: list[tuple[int, SavedSourceLead]] = []
    with open_read_only_store(db_path) as store:
        with read_snapshot_connection(store.connection):
            rows = store.connection.execute(
                "SELECT run_id, artifact_key FROM v2_artifacts WHERE artifact_type = ? "
                "AND run_id != ? ORDER BY created_at DESC LIMIT 20",
                ("V2FinalResearchOutput", str(run_id)),
            ).fetchall()
            for origin, key in rows:
                artifact = read_v2_artifact(store.connection, UUID(origin), key)
                output = V2FinalResearchOutput.model_validate_json(artifact.payload_json)
                if str(output.run_id) != origin:
                    raise ValueError("saved source output belongs to a different run")
                doi_by_source: dict[UUID, str] = {}
                for number in sorted({s.discovery_round for s in output.all_surviving_sources}):
                    try:
                        discovered = read_v2_artifact(
                            store.connection, UUID(origin), discovery_round_keys(number)[0]
                        )
                    except KeyError:
                        continue
                    discovery = V2DiscoveryScoutOutput.model_validate_json(discovered.payload_json)
                    if discovery.run_id != output.run_id:
                        raise ValueError("saved discovery metadata belongs to another run")
                    items = {item.item_id: item for item in discovery.items}
                    for cluster in discovery.clusters:
                        dois: set[str] = set()
                        for item_id in cluster.item_ids:
                            doi = items[item_id].doi
                            if doi and len(doi) <= 512:
                                try:
                                    dois.add(normalize_doi(doi))
                                except ValueError:
                                    continue
                        if len(dois) == 1:
                            doi_by_source[cluster.cluster_id] = next(iter(dois))
                for source in output.all_surviving_sources:
                    if not source.title or len(source.source_url) > 4000:
                        continue
                    overlap = len(words & set(re.findall(r"[a-z]{4,}", source.title.lower())))
                    if overlap < min(2, len(words)) or not overlap:
                        continue
                    ranked.append(
                        (
                            overlap,
                            SavedSourceLead(
                                origin_run_id=output.run_id,
                                origin_source_id=source.source_id,
                                title=source.title[:2000],
                                source_url=source.source_url,
                                doi=doi_by_source.get(source.source_id),
                            ),
                        )
                    )
    result: list[SavedSourceLead] = []
    seen: set[str] = set()
    for _score, lead in sorted(ranked, key=lambda row: -row[0]):
        identities = {"url:" + canonical_discovery_url(lead.source_url)}
        if lead.doi:
            identities.add("doi:" + lead.doi)
        if not identities.intersection(seen):
            seen.update(identities)
            result.append(lead)
        if len(result) == 12:
            break
    return tuple(result)
