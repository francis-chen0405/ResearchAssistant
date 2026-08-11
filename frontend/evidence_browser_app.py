"""Local read-only Streamlit evidence browser for persisted runs."""

from __future__ import annotations

from pathlib import Path
from uuid import UUID

from evidence_browser import EvidenceBrowserFilter, EvidenceStage, browse_evidence_run


def _load_streamlit() -> object:
    """Import Streamlit only when the local UI is launched."""
    try:
        import streamlit as st
    except ImportError as exc:  # pragma: no cover - environment guard
        raise RuntimeError("Streamlit is required to launch the local evidence browser") from exc
    return st


def main() -> None:
    """Render only read-only evidence inspection controls and artifacts."""
    st = _load_streamlit()
    st.set_page_config(page_title="ResearchAssistant Evidence Browser", layout="wide")
    st.title("Evidence Browser")
    st.caption(
        "Read-only inspection. Snapshot text is trusted only after ResearchAssistant normalization."
    )
    db_path = st.text_input("Existing SQLite database")
    run_id_text = st.text_input("Run ID")
    stance = st.selectbox("Stance", ["All", "supporting", "opposing"])
    stage = st.selectbox("Stage", ["All", *[item.value for item in EvidenceStage]])
    source_url = st.text_input("Exact source URL")
    approval = st.selectbox("Approval state", ["All", "Approved", "Rejected"])
    release = st.selectbox("Release status", ["All", "Released", "Not released"])
    if not st.button("Open evidence trail", use_container_width=True):
        return
    try:
        browser = browse_evidence_run(
            Path(db_path),
            UUID(run_id_text),
            EvidenceBrowserFilter(
                stance=None if stance == "All" else stance,
                stage=None if stage == "All" else EvidenceStage(stage),
                source_url=source_url or None,
                approved={"Approved": True, "Rejected": False}.get(approval),
                released={"Released": True, "Not released": False}.get(release),
            ),
        )
    except ValueError as exc:
        st.error(str(exc))
        return
    st.subheader(browser.manifest.raw_claim)
    st.info(browser.trusted_snapshot_text_label)
    st.caption(browser.provider_metadata_label)
    st.warning(browser.source_text_label)
    for trail in browser.trails:
        with st.expander(f"{trail.artifact_label} · {trail.candidate.source_url}"):
            st.markdown(f"**Exact quotation:** {trail.candidate.extracted_quote_block}")
            st.markdown("**Trusted snapshot text**")
            st.text(trail.snapshot.normalized_text)
            st.json(trail.snapshot.media_type_provenance.model_dump(mode="json"))
            if trail.analyst_decision is not None:
                st.write("Analyst approved:", trail.analyst_decision.approved)
            for review in trail.reviewer_decisions:
                st.write("Reviewer approved:", review.approved, "—", review.rationale)
            for ledger in trail.ledger_records:
                st.success(f"Ledger statement: {ledger.approved_factual_statement}")
    if browser.released_statement_traces:
        st.subheader("Released factual statements")
        for trace in browser.released_statement_traces:
            st.write(trace.ledger_record.approved_factual_statement)


if __name__ == "__main__":  # pragma: no cover - Streamlit entry point
    main()
