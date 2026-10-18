"""Read-only verification of persisted final-output identity and released text."""

from __future__ import annotations

from hashlib import sha256
from uuid import UUID

from researchassistant.contracts.models import RunManifest, V2FinalResearchOutput


def validate_saved_output(
    output: V2FinalResearchOutput, run_id: UUID, manifest: RunManifest
) -> V2FinalResearchOutput:
    """Verify original hashes without changing historical payloads or release decisions."""
    if output.run_id != run_id or manifest.run_id != run_id:
        raise ValueError("final output run differs from its requested run")
    if output.exact_claim != manifest.raw_claim:
        raise ValueError("final output exact claim differs from its saved run")
    if output.release_validation.valid:
        from researchassistant.agents.v2_final_output import render_v2_final_output

        rendered = render_v2_final_output(output)
        if (
            sha256(rendered.encode("utf-8")).hexdigest()
            != output.release_validation.rendered_output_hash
        ):
            raise ValueError("released v2 brief hash does not match reconstructed brief")
    return output
