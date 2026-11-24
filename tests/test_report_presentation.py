from itertools import combinations

from researchassistant.contracts.model_evidence import V2EvidenceRelationship
from researchassistant.evidence.report_presentation import claim_status


def _item(relationship: V2EvidenceRelationship) -> object:
    """Build the small part of a display item consumed by claim_status."""
    return type("EvidenceItem", (), {"relationship_to_claim": relationship})()


def test_claim_status_summarizes_every_recorded_relationship_combination() -> None:
    ordered_relationships = tuple(V2EvidenceRelationship)
    phrases = {
        V2EvidenceRelationship.SUPPORTS: "supporting",
        V2EvidenceRelationship.CHALLENGES: "challenging",
        V2EvidenceRelationship.QUALIFIES: "qualifying",
        V2EvidenceRelationship.UNRELATED: "unrelated",
    }

    for size in range(len(ordered_relationships) + 1):
        for relationships in combinations(ordered_relationships, size):
            status = claim_status(_item(relationship) for relationship in relationships)

            if not relationships:
                assert status == "Claim not established by the admitted evidence"
            else:
                expected = " and ".join(phrases[relationship] for relationship in relationships)
                assert status == f"{expected.capitalize()} evidence admitted; claim not established"
            assert "claim established" not in status.lower()


def test_claim_status_is_not_skewed_toward_challenges_when_support_is_also_admitted() -> None:
    items = (_item(V2EvidenceRelationship.SUPPORTS) for _ in range(8))
    items = (*items, *(_item(V2EvidenceRelationship.CHALLENGES) for _ in range(2)))

    assert claim_status(items) == (
        "Supporting and challenging evidence admitted; claim not established"
    )
