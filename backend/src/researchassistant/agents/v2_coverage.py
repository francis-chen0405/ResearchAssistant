"""Application-owned exact-claim focus for fresh planning, without claim inference."""

import re

from researchassistant.contracts.models import (
    V2ClaimCoverageDimension,
    V2ClaimCoverageFocus,
    V2ClaimCoverageKind,
)


def claim_component_focus(
    exact_claim: str,
    focus: tuple[V2ClaimCoverageFocus, ...],
    *,
    require_exact_components: bool = False,
) -> tuple[V2ClaimCoverageFocus, ...]:
    claim_folded = exact_claim.casefold()
    asserted = tuple(
        item
        for item in focus
        if not require_exact_components
        or re.search(
            r"(?<!\w)" + re.escape(item.claim_component.casefold()) + r"(?!\w)",
            claim_folded,
        )
    )
    if any(item.dimension is V2ClaimCoverageDimension.EFFECT_OR_ASSOCIATION for item in asserted):
        return asserted
    return (
        V2ClaimCoverageFocus(
            dimension=V2ClaimCoverageDimension.EFFECT_OR_ASSOCIATION,
            claim_component=exact_claim,
            kind=V2ClaimCoverageKind.CLAIM_COMPONENT,
        ),
        *asserted,
    )
