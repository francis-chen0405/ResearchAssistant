"""Physical discovery completions retain exact owning operation on every read."""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from pathlib import Path

import pytest
import test_product_discovery_pipeline as product
from fastapi.testclient import TestClient
from test_mlp3_api import FakeServices

from researchassistant.api.api import ApiRuntime, create_app
from researchassistant.api.live_service import LiveResearchController
from researchassistant.contracts.discovery_v2 import V2ProviderAttemptCompletion
from researchassistant.contracts.models import (
    DiscoveryProvider,
    ResearchControls,
    canonical_v2_artifact_json,
    v2_payload_fingerprint,
)
from researchassistant.storage.discovery_store import (
    complete_provider_attempt,
    compute_discovery_audit_counters,
    inspect_discovery_run,
    provider_attempt_audit,
)
from researchassistant.storage.query_retrieval_store import read_pages
from researchassistant.storage.source_leads import read_source_leads


@pytest.mark.parametrize(
    "consumer", ["audit", "counters", "inspection", "status", "pages", "leads", "replay"]
)
def test_other_existing_operation_cannot_own_completion(tmp_path: Path, consumer: str) -> None:
    path = tmp_path / "generated.sqlite3"
    result, _, _ = product._run(
        path, ResearchControls(discovery_providers=(DiscoveryProvider.EXA,))
    )
    assert result.state.value == "released", result.failure_reason
    audit = provider_attempt_audit(path, result.run_id)
    original = next(item for item in audit.completions if item is not None)
    other = next(item for item in audit.starts if item.operation_id != original.operation_id)
    assert all(
        completion is None or completion.operation_id == start.operation_id
        for start, completion in zip(audit.starts, audit.completions, strict=True)
    )
    counters = compute_discovery_audit_counters(path, result.run_id)
    assert counters.http_requests == len(audit.starts)
    assert counters.unknown_requests == 0
    forged = V2ProviderAttemptCompletion.model_validate(
        original.model_dump() | {"operation_id": other.operation_id}
    )
    payload = canonical_v2_artifact_json(forged)
    # Simulate checksum-valid corruption in a disposable generated database,
    # then restore its original trigger before exercising public inspection.
    with sqlite3.connect(path) as connection:
        trigger = connection.execute(
            "SELECT sql FROM sqlite_master WHERE name='v2_artifacts_immutable_update'"
        ).fetchone()[0]
        connection.execute("DROP TRIGGER v2_artifacts_immutable_update")
        updated = connection.execute(
            "UPDATE v2_artifacts SET payload_json=?, payload_sha256=? "
            "WHERE run_id=? AND artifact_type='V2ProviderAttemptCompletion' "
            "AND json_extract(payload_json, '$.attempt_id')=?",
            (
                payload,
                v2_payload_fingerprint(payload),
                str(result.run_id),
                str(original.attempt_id),
            ),
        )
        assert updated.rowcount == 1
        connection.execute(trigger)
    before = path.read_bytes(), path.stat().st_mtime_ns
    controller = LiveResearchController(environment={})
    readers: dict[str, Callable[[], object]] = {
        "audit": lambda: provider_attempt_audit(path, result.run_id),
        "counters": lambda: compute_discovery_audit_counters(path, result.run_id),
        "inspection": lambda: inspect_discovery_run(str(path), result.run_id),
        "status": lambda: controller.snapshot(path, result.run_id),
        "pages": lambda: read_pages(path, result.run_id),
        "leads": lambda: read_source_leads(path, result.run_id),
        "replay": lambda: complete_provider_attempt(str(path), original, original.completed_at),
    }
    try:
        with pytest.raises(sqlite3.IntegrityError, match="conflicting operation ownership"):
            readers[consumer]()
        if consumer == "status":
            client = TestClient(
                create_app(
                    ApiRuntime(controller=controller, services=FakeServices(), environment={}),
                    load_keychain_on_start=False,
                    allowed_hosts=("testserver",),
                ),
                raise_server_exceptions=False,
            )
            response = client.get(f"/api/research/{result.run_id}", params={"db_path": str(path)})
            # Status inspection retains its existing generic server-error
            # boundary for SQLite integrity failures; no release is returned.
            assert response.status_code == 500, response.text
            assert response.text == "Internal Server Error"
        assert (path.read_bytes(), path.stat().st_mtime_ns) == before
    finally:
        assert controller.shutdown(timeout=20)
