"""Read and authenticate saved neighborhood bytes without dispatching execution."""

from __future__ import annotations

import httpx

from researchassistant.contracts.discovery_v2 import V2DiscoveryOperation, V2GraphNeighborAction
from researchassistant.contracts.neighborhood import (
    V2NeighborhoodCheckpoint,
    V2NeighborhoodResponse,
)
from researchassistant.contracts.neighborhood_results import NeighborhoodRelation
from researchassistant.providers.openalex_neighborhood import OpenAlexNeighborhoodAdapter
from researchassistant.storage.store import read_v2_artifact


class MissingNeighborhoodCheckpoint(ValueError):
    """A saved parser checkpoint is absent; only an executor may dispatch it."""


def read_neighborhood_checkpoint(
    path: str, action: V2GraphNeighborAction, phase: str
) -> V2NeighborhoodCheckpoint:
    from researchassistant.storage.discovery_store import (
        provider_attempt_audit,
        read_discovery_artifacts,
    )

    key = f"graph-parser/{action.artifact_id}/{phase}"
    try:
        cp = V2NeighborhoodCheckpoint.model_validate_json(
            read_v2_artifact(
                path, action.run_id, f"source-discovery-v1:V2NeighborhoodCheckpoint:{key}"
            ).payload_json
        )
        if cp.action != action:
            raise ValueError("Neighborhood parser checkpoint action differs")
        audit = provider_attempt_audit(path, action.run_id)
        complete = next((x for x in audit.completions if x and x.attempt_id == cp.attempt_id), None)
        if (
            not complete
            or complete.status != "completed"
            or complete.response_hash != cp.response_hash
        ):
            raise ValueError("Neighborhood parser lacks completed physical response")
        try:
            body = V2NeighborhoodResponse.model_validate_json(
                read_v2_artifact(
                    path,
                    action.run_id,
                    f"source-discovery-v1:V2NeighborhoodResponse:graph-response/{cp.attempt_id}",
                ).payload_json
            )
        except KeyError:
            body = None
        start = next((x for x in audit.starts if x.artifact_id == cp.attempt_id), None)
        if start is None:
            raise ValueError("Neighborhood checkpoint lacks durable request")
        if phase == "identity" and start.request_kind != "identity":
            raise ValueError("Seed identity checkpoint requires an exact identity request")
        owned_operation = next(
            (
                item
                for item in read_discovery_artifacts(path, action.run_id)
                if isinstance(item, V2DiscoveryOperation)
                and item.action.artifact_id == start.operation_id
            ),
            None,
        )
        if (
            owned_operation is None
            or not isinstance(owned_operation.action, V2GraphNeighborAction)
            or owned_operation.action.seed != action.seed
            or owned_operation.action.provider != action.provider
            or complete.operation_id != start.operation_id
            or (
                phase == "neighbors"
                and start.request_kind == "primary"
                and owned_operation.action != action
            )
        ):
            raise ValueError("Neighborhood response differs from owned seed/action request")
        if body is not None and (
            body.run_id != action.run_id
            or body.attempt_id != cp.attempt_id
            or body.operation_id != start.operation_id
            or body.response_hash != cp.response_hash
        ):
            raise ValueError("Exact provider body differs from completed response")
        if phase == "identity":
            if body is None:
                raise ValueError("Identity checkpoint lacks exact provider response")
            parsed = OpenAlexNeighborhoodAdapter.parse_resolution(
                action.seed.work.provider_work_id or action.seed.work.doi or "",
                httpx.Response(200, content=body.content.encode()),
            )
        elif (
            body is not None
            and next(x for x in audit.starts if x.artifact_id == cp.attempt_id).request_kind
            == "primary"
        ):
            if cp.work is None:
                raise ValueError("Neighbor checkpoint lacks exact identity")
            identity = read_neighborhood_checkpoint(path, action, "identity")
            if cp.work != identity.work:
                raise ValueError("Neighbor checkpoint differs from exact resolved seed")
            start = next(x for x in audit.starts if x.artifact_id == cp.attempt_id)
            parsed = OpenAlexNeighborhoodAdapter.parse_expansion(
                cp.work,
                NeighborhoodRelation(action.relationship),
                limit=start.requested_records,
                response=httpx.Response(200, content=body.content.encode()),
            )
        else:
            # No neighbor HTTP request for absent/empty relationship fields.
            identity = read_neighborhood_checkpoint(path, action, "identity")
            if cp.work != identity.work or cp.work is None or cp.results:
                raise ValueError("No-request neighbor checkpoint differs from exact seed")
            field = (
                cp.work.referenced_work_ids
                if action.relationship == "references"
                else cp.work.related_work_ids
            )
            if (
                action.relationship == "citing"
                or (field and len(field) > 0)
                or cp.status != ("unsupported" if field is None else "empty")
            ):
                raise ValueError("No-request relationship disposition differs from provider field")
            return cp
        if (
            parsed.work != cp.work
            or parsed.results != cp.results
            or parsed.status.value != cp.status
        ):
            raise ValueError("Parser checkpoint differs from exact provider response")
        return cp
    except KeyError:
        pass
    if phase == "identity":
        for prior in read_discovery_artifacts(path, action.run_id):
            if (
                isinstance(prior, V2NeighborhoodCheckpoint)
                and prior.phase == "identity"
                and prior.action.seed == action.seed
            ):
                audit = provider_attempt_audit(path, action.run_id)
                if not any(
                    x
                    and x.status == "completed"
                    and x.attempt_id == prior.attempt_id
                    and x.response_hash == prior.response_hash
                    for x in audit.completions
                ):
                    raise ValueError("Shared seed resolution lacks physical ownership")
                return read_neighborhood_checkpoint(path, prior.action, "identity")
    raise MissingNeighborhoodCheckpoint(
        "Missing checkpoint cannot be replayed without configured transport"
    )
