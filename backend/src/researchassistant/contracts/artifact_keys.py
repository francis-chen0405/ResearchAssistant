"""Stable persisted stage keys shared by execution and readers."""

V2_ACQUISITION_PROBE_ARTIFACT_KEY = "phase-5-acquisition-probe"


def discovery_round_keys(round_number: int) -> tuple[str, str]:
    if round_number == 1:
        return "phase-4-discovery-scout", "phase-5-acquisition-probe"
    if round_number == 4:
        return (
            "post-phase-13-round-4-discovery-scout-v1",
            "post-phase-13-round-4-acquisition-probe-v1",
        )
    return (
        f"phase-7-round-{round_number}-discovery-scout",
        f"phase-7-round-{round_number}-acquisition-probe",
    )


PHASE9_POST_FILTER_VERSION = "mlp4-expanded-retrieval-yield-v1"
PHASE9_LEDGER_ID_VERSION = "phase9-provider-ledger-id-v1"
PHASE9_RESEARCHERS_ARTIFACT = "phase9-researchers"
PHASE9_ANALYSIS_ARTIFACT = "phase9-analysis-ledger"
PHASE9_PLANNER_CHECKPOINT = "planner"
PHASE9_RESEARCHERS_CHECKPOINT = "researchers"
PHASE9_ANALYSIS_CHECKPOINT = "analysis-ledger"
PHASE9_SYNTHESIS_CHECKPOINT = "synthesis"
PHASE9_VALIDATION_CHECKPOINT = "validation-release"
MVP10_TARGETED_PLANNER_CHECKPOINT = "mvp10-targeted-planner"
MVP10_TARGETED_RESEARCHERS_CHECKPOINT = "mvp10-targeted-researchers"
MVP10_TARGETED_ANALYSIS_CHECKPOINT = "mvp10-targeted-analysis"
MVP10_TARGETED_PLANNER_ARTIFACT = "mvp10-targeted-planner"
MVP10_TARGETED_RESEARCHERS_ARTIFACT = "mvp10-targeted-researchers"
MVP10_TARGETED_ANALYSIS_ARTIFACT = "mvp10-targeted-analysis"
MVP11_ROUND_TWO_PLANNER_CHECKPOINT = "mvp11-round-two-planner"
MVP11_ROUND_TWO_RESEARCHERS_CHECKPOINT = "mvp11-round-two-researchers"
MVP11_ROUND_TWO_ANALYSIS_CHECKPOINT = "mvp11-round-two-analysis"
MVP11_ROUND_THREE_PLANNER_CHECKPOINT = "mvp11-round-three-planner"
MVP11_ROUND_THREE_RESEARCHERS_CHECKPOINT = "mvp11-round-three-researchers"
MVP11_ROUND_THREE_ANALYSIS_CHECKPOINT = "mvp11-round-three-analysis"
