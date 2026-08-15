"""Polished local Streamlit surface for the persisted MVP-4 live pipeline."""

from __future__ import annotations

import atexit
import os
import sys
from decimal import Decimal, InvalidOperation
from pathlib import Path
from uuid import UUID

from pydantic import ValidationError

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from frontend.live_service import (  # noqa: E402
    LiveResearchController,
    LiveRunRequest,
    LiveRunSnapshot,
    prepare_default_database,
)
from frontend.service_manager import WigoloServiceManager  # noqa: E402
from models import DEFAULT_RESEARCH_CONTROLS  # noqa: E402


def main() -> None:
    st = _load_streamlit()
    st.set_page_config(
        page_title="ResearchAssistant Live",
        page_icon="◈",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    _styles(st)

    @st.cache_resource
    def controller() -> LiveResearchController:
        return LiveResearchController(environment=os.environ)

    @st.cache_resource
    def service_manager() -> WigoloServiceManager:
        manager = WigoloServiceManager(base_environment=os.environ)
        atexit.register(manager.stop)
        return manager

    live = controller()
    services = service_manager()
    default_db = prepare_default_database()

    st.markdown('<div class="eyebrow">LOCAL · LIVE · PERSISTED</div>', unsafe_allow_html=True)
    st.title("Research Assistant")
    st.caption(
        "Evidence-constrained research through Exa discovery, pinned Wigolo 0.2.1 "
        "acquisition, optional Firecrawl fallback, and direct Xiaomi MiMo "
        "`mimo-v2.5-pro`. Public, non-sensitive claims only."
    )
    st.warning(
        "Human review is required before any external or high-stakes use. A released hash "
        "proves deterministic validation—not factual infallibility."
    )

    with st.sidebar:
        st.subheader("Local services")
        diagnostic = services.probe()
        _render_service_status(st, diagnostic)
        start_col, stop_col = st.columns(2)
        if start_col.button(
            "Start stack",
            use_container_width=True,
            disabled=diagnostic.wigolo_ready or diagnostic.state == "wrong_service",
        ):
            diagnostic = services.start()
            st.rerun()
        if stop_col.button(
            "Stop owned",
            use_container_width=True,
            disabled=not diagnostic.owned_process or live.has_active_runs(),
        ):
            services.stop()
            st.rerun()
        if diagnostic.recent_output:
            with st.expander("Redacted startup details"):
                st.code("\n".join(diagnostic.recent_output[-12:]), language=None)
        st.divider()
        st.subheader("Configuration")
        config_error = live.configuration_message()
        if config_error:
            st.error("A required provider is not configured for this server process.")
            st.caption(config_error)
            st.caption(
                "Launch with `MIMO_API_KEY` and `EXA_API_KEY`. Firecrawl is optional. "
                "Keys are never sent to this page, SQLite, logs, URLs, or arguments."
            )
        else:
            st.success("Exa search and direct MiMo configuration present")
            fallback = "enabled" if os.environ.get("FIRECRAWL_API_KEY", "").strip() else "disabled"
            st.caption(
                f"Key values hidden · Firecrawl fallback {fallback} · model pinned to mimo-v2.5-pro"
            )
        st.divider()
        st.caption(
            "The Streamlit server must remain running while this website is open. Closing "
            "the server can interrupt an active synchronous run; arbitrary crash recovery "
            "is not promised."
        )

    input_tab, history_tab = st.tabs(["New or resumed research", "Run history"])
    with input_tab:
        _render_start_form(st, live, diagnostic.wigolo_ready, config_error, default_db)
    with history_tab:
        _render_history(st, live, default_db)

    selected_run = st.session_state.get("mvp5_selected_run_id")
    selected_db = st.session_state.get("mvp5_selected_db_path")
    if selected_run and selected_db:
        st.divider()
        _render_live_fragment(st, live, selected_db, UUID(selected_run))


def _render_start_form(
    st: object,
    controller: LiveResearchController,
    wigolo_ready: bool,
    config_error: str | None,
    default_db: Path,
) -> None:
    st.subheader("Start research")
    with st.form("mvp5-live-start", clear_on_submit=False):
        claim = st.text_area(
            "Exact claim",
            height=120,
            placeholder=(
                "Enter one precise public, non-sensitive claim without leading/trailing spaces."
            ),
        )
        budget_col, cost_col, calls_col = st.columns(3)
        max_tokens = budget_col.number_input(
            "Token ceiling", min_value=1, max_value=1_000_000, value=200_000, step=10_000
        )
        max_cost = cost_col.text_input("MiMo cost ceiling (USD)", value="0.15")
        max_calls = calls_col.number_input(
            "Physical MiMo call ceiling", min_value=1, max_value=160, value=160, step=1
        )
        database = st.text_input("SQLite database", value=str(default_db))
        run_id_text = st.text_input(
            "Run ID (optional)",
            placeholder="Leave blank for a new UUID; reuse only for exact resume.",
        )
        acknowledged = st.checkbox(
            "I confirm this claim is public/non-sensitive and I will human-review the result."
        )
        submitted = st.form_submit_button(
            "Start Research",
            type="primary",
            use_container_width=True,
            disabled=bool(config_error) or not wigolo_ready,
        )
    if not submitted:
        if not wigolo_ready:
            st.info("Start or restore healthy pinned Wigolo before research can begin.")
        return
    if not acknowledged:
        st.error(
            "Confirm that the claim is public/non-sensitive and that you will "
            "human-review the result before starting research."
        )
        return
    try:
        run_id = UUID(run_id_text) if run_id_text.strip() else None
        cost = Decimal(max_cost)
        request = LiveRunRequest(
            raw_claim=claim,
            db_path=str(Path(database).expanduser().resolve()),
            run_id=run_id,
            max_tokens=int(max_tokens),
            max_cost_usd=cost,
            max_llm_calls=int(max_calls),
            research_controls=DEFAULT_RESEARCH_CONTROLS,
        )
    except (ValueError, InvalidOperation, ValidationError) as exc:
        st.error(f"Invalid input: {exc}")
        return
    result = controller.start(request)
    st.session_state["mvp5_selected_run_id"] = str(result.run_id)
    st.session_state["mvp5_selected_db_path"] = request.db_path
    if result.started:
        st.success(result.message)
    elif result.classification == "duplicate_active":
        st.info(result.message)
    else:
        st.error(result.message)


def _render_history(st: object, controller: LiveResearchController, default_db: Path) -> None:
    history_db = st.text_input("History database", value=str(default_db), key="mvp5-history-db")
    try:
        items = controller.history(history_db)
    except Exception as exc:
        st.error(f"Could not read run history: {exc}")
        return
    if not items:
        st.info("No persisted runs in this database yet.")
        return
    selected = st.selectbox(
        "Inspect persisted run",
        items,
        format_func=lambda item: (
            f"{item.status.upper()} · {str(item.run_id)[:8]} · {item.raw_claim[:72]}"
        ),
    )
    if st.button("Open run", use_container_width=True):
        st.session_state["mvp5_selected_run_id"] = str(selected.run_id)
        st.session_state["mvp5_selected_db_path"] = str(Path(history_db).expanduser().resolve())
        st.rerun()
    st.dataframe(
        [item.model_dump(mode="json") for item in items],
        hide_index=True,
        use_container_width=True,
    )


def _render_live_fragment(
    st: object,
    controller: LiveResearchController,
    db_path: str,
    run_id: UUID,
) -> None:
    @st.fragment(run_every=2)
    def live_status() -> None:
        try:
            snapshot = controller.snapshot(db_path, run_id)
        except KeyError as exc:
            st.error(str(exc))
            return
        _render_snapshot(st, controller, snapshot)

    live_status()


def _render_snapshot(
    st: object,
    controller: LiveResearchController,
    snapshot: LiveRunSnapshot,
) -> None:
    st.subheader("Authoritative run status")
    if snapshot.classification == "released":
        st.success(snapshot.message)
    elif snapshot.classification in {"starting", "running", "duplicate_active"}:
        st.info(snapshot.message)
    elif snapshot.classification == "cancelled":
        st.warning(snapshot.message)
    else:
        st.error(snapshot.message)

    status_col, stage_col, checkpoint_col, cost_col = st.columns(4)
    status_col.metric("Status", snapshot.classification)
    stage_col.metric("Stage", snapshot.stage)
    checkpoint_col.metric(
        "Checkpoint",
        f"{snapshot.completed_checkpoints}/{snapshot.total_checkpoints} complete",
        snapshot.latest_checkpoint or "none",
    )
    cost_col.metric(
        "MiMo accounted cost",
        (
            f"${snapshot.total_cost_usd:.6f}"
            if snapshot.cost_usage_complete and snapshot.total_cost_usd is not None
            else f"incomplete (known ${snapshot.known_cost_subtotal_usd:.6f})"
        ),
    )
    calls_col, tokens_col, retrieval_col, exit_col = st.columns(4)
    calls_col.metric("MiMo calls", snapshot.model_calls_used)
    tokens_col.metric(
        "Tokens",
        (
            snapshot.total_tokens
            if snapshot.token_usage_complete and snapshot.total_tokens is not None
            else f"incomplete (known {snapshot.known_token_subtotal})"
        ),
    )
    retrieval_col.metric("Retrievals", snapshot.retrieval_attempts_used)
    exit_col.metric("Exit code", snapshot.exit_code if snapshot.exit_code is not None else "—")

    support_col, oppose_col = st.columns(2)
    _render_progress_card(support_col, snapshot.supporting, "Supporting research")
    _render_progress_card(oppose_col, snapshot.opposing, "Opposing research")

    st.caption(f"Run ID: `{snapshot.run_id}` · Database: `{snapshot.db_path}`")
    st.caption(f"Diagnostic component: `{snapshot.diagnostic_component}`")
    st.write("**Exact claim:**", snapshot.raw_claim)
    if snapshot.fingerprint:
        with st.expander("Compatibility identity"):
            st.code(
                "\n".join(
                    (
                        f"provider: {snapshot.provider_identity}",
                        f"model: {snapshot.model_identity}",
                        f"fingerprint: {snapshot.fingerprint}",
                    )
                ),
                language=None,
            )
    if snapshot.validation_errors:
        st.subheader("Validation errors")
        for error in snapshot.validation_errors:
            st.error(error)

    if snapshot.classification == "running":
        if st.button("Cancel Research", type="secondary"):
            try:
                st.warning(controller.cancel(snapshot.db_path, snapshot.run_id))
            except ValueError as exc:
                st.error(str(exc))
    elif snapshot.classification == "failed":
        st.info(
            "A failed terminal run may be reinvoked only with the same run ID, byte-exact "
            "claim, budgets, and complete compatibility fingerprint. Otherwise use a new run ID."
        )

    if snapshot.final_brief is not None:
        st.warning("Human review is mandatory before using or sharing this released brief.")
        st.subheader("Validated final brief")
        st.code(snapshot.final_brief, language=None)
        st.caption(f"SHA-256: `{snapshot.rendered_brief_hash}`")
        st.download_button(
            "Download brief",
            data=snapshot.final_brief,
            file_name=f"research-brief-{snapshot.run_id}.md",
            mime="text/markdown",
            use_container_width=True,
        )


def _render_progress_card(container: object, progress: object, title: str) -> None:
    with container:
        st = container
        st.markdown(f"#### {title}")
        st.caption(progress.status)
        metric_col, snapshot_col, candidate_col = st.columns(3)
        metric_col.metric("Model attempts", progress.model_attempts)
        snapshot_col.metric("Snapshots", progress.usable_snapshots)
        candidate_col.metric("Candidates", progress.candidates)


def _render_service_status(st: object, diagnostic: object) -> None:
    if diagnostic.wigolo_ready:
        st.success("Wigolo 0.2.1 healthy")
    elif diagnostic.state == "starting":
        st.info("Stack starting")
    elif diagnostic.state == "wrong_service":
        st.error("Port belongs to another service")
    else:
        st.warning("Stack not ready")
    st.caption(diagnostic.message)


def _styles(st: object) -> None:
    st.markdown(
        """
        <style>
        .stApp { background: linear-gradient(150deg, #f7f5ef 0%, #edf4f2 55%, #e8eff5 100%); }
        .block-container { max-width: 1180px; padding-top: 2.4rem; }
        .eyebrow { color: #22625c; letter-spacing: .18em; font-size: .72rem; font-weight: 750; }
        h1, h2, h3 { color: #172927; letter-spacing: -.025em; overflow-wrap: anywhere; }
        [data-testid="stMetric"] { background: rgba(255,255,255,.72); border: 1px solid #d7e2df;
          padding: .75rem 1rem; border-radius: 14px; box-shadow: 0 10px 30px rgba(31,65,61,.06); }
        [data-testid="stSidebar"] { background: #172927; }
        [data-testid="stSidebar"] * { color: #edf7f5; }
        [data-testid="stSidebar"] .stAlert * { color: inherit; }
        [data-testid="stSidebar"] .stButton button { background: #edf7f5; border-color: #b8ccc8; }
        [data-testid="stSidebar"] .stButton button p { color: #172927; }
        .stButton > button[kind="primary"], .stFormSubmitButton > button[kind="primary"] {
          background: #176b62; border-color: #176b62; border-radius: 12px; font-weight: 700; }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _load_streamlit() -> object:
    try:
        import streamlit as st
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "Streamlit is not installed. Install declared project dependencies first."
        ) from exc
    return st


if __name__ == "__main__":
    main()
