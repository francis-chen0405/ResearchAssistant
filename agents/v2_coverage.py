"""Application-owned exact-claim focus for fresh planning, without claim inference."""

from models import V2ClaimCoverageDimension, V2ClaimCoverageFocus, V2ClaimCoverageKind


def claim_component_focus(
    exact_claim: str, focus: tuple[V2ClaimCoverageFocus, ...]
) -> tuple[V2ClaimCoverageFocus, ...]:
    if any(item.dimension is V2ClaimCoverageDimension.EFFECT_OR_ASSOCIATION for item in focus):
        return focus
    return (
        V2ClaimCoverageFocus(
            dimension=V2ClaimCoverageDimension.EFFECT_OR_ASSOCIATION,
            claim_component=exact_claim,
            kind=V2ClaimCoverageKind.CLAIM_COMPONENT,
        ),
        *focus,
    )
