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

from credential_store import (  # noqa: E402
    KeychainUnavailableError,
    ProviderCredentials,
    apply_credentials_to_environment,
    load_saved_credentials_into_environment,
    save_credentials,
)
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
        initial_sidebar_state="collapsed",
    )
    _styles(st)

    if (
        not os.environ.get("MIMO_API_KEY", "").strip()
        or not os.environ.get("EXA_API_KEY", "").strip()
    ) and os.environ.get("RESEARCHASSISTANT_DISABLE_KEYCHAIN") != "1":
        load_saved_credentials_into_environment()

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
    diagnostic = services.probe()
    config_error = live.configuration_message()
    _initialize_ui_state(st, default_db)
    _render_navigation(st)
    _render_provider_setup_dialog(st, controller)

    if st.session_state.get("mlp2_setup_saved"):
        st.toast("Provider keys saved securely in macOS Keychain.")
        st.session_state["mlp2_setup_saved"] = False

    if st.session_state["mlp2_view"] == "history":
        _render_history_page(st, live, default_db)
    else:
        _render_research_page(
            st,
            live,
            services,
            diagnostic,
            config_error,
            default_db,
        )

    selected_run = st.session_state.get("mvp5_selected_run_id")
    selected_db = st.session_state.get("mvp5_selected_db_path")
    if selected_run and selected_db:
        st.divider()
        _render_live_fragment(st, live, selected_db, UUID(selected_run))


def _initialize_ui_state(st: object, default_db: Path) -> None:
    defaults = (
        ("mlp2_view", "research"),
        ("mlp2_advanced", False),
        ("mlp2_provider_setup", False),
        ("mlp2_setup_saved", False),
        ("mlp2_max_tokens", 200_000),
        ("mlp2_max_cost", "0.15"),
        ("mlp2_max_calls", 160),
        ("mlp2_database", str(default_db)),
        ("mlp2_run_id", ""),
    )
    for key, value in defaults:
        if key not in st.session_state:
            st.session_state[key] = value


def _render_navigation(st: object) -> None:
    brand, spacer, history_column, setup_column, advanced_column = st.columns(
        (2.4, 3.8, 1.0, 1.45, 1.25), vertical_alignment="center"
    )
    brand.markdown('<div class="brand">ResearchAssistant</div>', unsafe_allow_html=True)
    spacer.markdown('<div class="local-pill">LOCAL · PRIVATE</div>', unsafe_allow_html=True)
    history_label = "Research" if st.session_state["mlp2_view"] == "history" else "History"
    if history_column.button(history_label, key="mlp2_history_button"):
        st.session_state["mlp2_view"] = (
            "research" if st.session_state["mlp2_view"] == "history" else "history"
        )
        st.rerun()
    if setup_column.button("Provider setup", key="mlp2_setup_button"):
        st.session_state["mlp2_provider_setup"] = True
        st.rerun()
    advanced_label = "Close advanced" if st.session_state["mlp2_advanced"] else "Advanced"
    if advanced_column.button(advanced_label, key="mlp2_advanced_button"):
        st.session_state["mlp2_advanced"] = not st.session_state["mlp2_advanced"]
        st.rerun()


def _render_provider_setup_dialog(st: object, controller_factory: object) -> None:
    if not st.session_state["mlp2_provider_setup"]:
        return

    @st.dialog("Provider setup")
    def provider_setup() -> None:
        st.caption(
            "Connect the local research providers. Keys are saved in your macOS Keychain, "
            "not in this project or its research database."
        )
        with st.form("mlp2-provider-setup", clear_on_submit=True):
            mimo_key = st.text_input("MiMo API key", type="password")
            exa_key = st.text_input("Exa API key", type="password")
            firecrawl_key = st.text_input(
                "Firecrawl API key (optional)",
                type="password",
                help="Enables the approved fallback when Wigolo cannot extract a public page.",
            )
            saved = st.form_submit_button(
                "Save provider keys", type="primary", use_container_width=True
            )
        if st.button("Cancel", key="mlp2_cancel_setup", use_container_width=True):
            st.session_state["mlp2_provider_setup"] = False
            st.rerun()
        if not saved:
            return
        try:
            credentials = ProviderCredentials(
                mimo_api_key=mimo_key,
                exa_api_key=exa_key,
                firecrawl_api_key=firecrawl_key or None,
            )
            save_credentials(credentials)
            apply_credentials_to_environment(credentials)
        except (ValidationError, KeychainUnavailableError):
            st.error("Could not save the provider keys. Check each value and try again.")
            return
        controller_factory.clear()
        st.session_state["mlp2_provider_setup"] = False
        st.session_state["mlp2_setup_saved"] = True
        st.rerun()

    provider_setup()


def _render_research_page(
    st: object,
    controller: LiveResearchController,
    services: WigoloServiceManager,
    diagnostic: object,
    config_error: str | None,
    default_db: Path,
) -> None:
    if st.session_state["mlp2_advanced"]:
        primary, advanced = st.columns((2.15, 1.0), gap="large")
        with primary:
            _render_hero(st)
            _render_start_form(st, controller, diagnostic.wigolo_ready, config_error, default_db)
        with advanced:
            _render_advanced_panel(
                st,
                controller,
                services,
                diagnostic,
                config_error,
                default_db,
            )
        return

    with st.container(key="mlp2_primary"):
        _render_hero(st)
        _render_start_form(st, controller, diagnostic.wigolo_ready, config_error, default_db)


def _render_hero(st: object) -> None:
    st.markdown(
        """
        <section class="hero">
          <div class="hero-kicker">Independent research, one clear brief.</div>
          <h1>Research the claim.<br><span>Not the noise.</span></h1>
          <p>See the strongest case on both sides, with the source material kept close.</p>
          <div class="research-stage" aria-hidden="true">
            <div class="stage-grid"></div>
            <div class="stage-glow"></div>
            <div class="stage-orbit"><span></span><span></span><span></span></div>
            <div class="signal-core"><i></i><b>R</b></div>
            <div class="signal-card signal-support">
              <span class="signal-dot"></span><small>SUPPORTING</small>
              <strong>Evidence mapped</strong>
              <em><i></i><i></i><i></i></em>
            </div>
            <div class="signal-card signal-oppose">
              <span class="signal-dot"></span><small>OPPOSING</small>
              <strong>Counterpoints found</strong>
              <em><i></i><i></i><i></i></em>
            </div>
            <div class="signal-card signal-citations">
              <span class="signal-dot"></span><small>SOURCES</small>
              <strong>Exact quotes kept</strong>
              <em><i></i><i></i><i></i></em>
            </div>
            <div class="stage-scan"></div>
          </div>
        </section>
        """,
        unsafe_allow_html=True,
    )


def _render_advanced_panel(
    st: object,
    controller: LiveResearchController,
    services: WigoloServiceManager,
    diagnostic: object,
    config_error: str | None,
    default_db: Path,
) -> None:
    with st.container(border=True):
        st.markdown('<div class="panel-eyebrow">ADVANCED MODE</div>', unsafe_allow_html=True)
        st.subheader("Run settings")
        st.caption("Technical limits and local runtime details for this run.")
        st.number_input(
            "Token ceiling",
            min_value=1,
            max_value=1_000_000,
            step=10_000,
            key="mlp2_max_tokens",
        )
        st.text_input("MiMo cost ceiling (USD)", key="mlp2_max_cost")
        st.number_input(
            "Physical MiMo call ceiling",
            min_value=1,
            max_value=160,
            step=1,
            key="mlp2_max_calls",
        )
        st.text_input("SQLite database", key="mlp2_database", placeholder=str(default_db))
        st.text_input(
            "Run ID (optional)",
            key="mlp2_run_id",
            placeholder="Leave blank for a new run.",
        )
        st.divider()
        st.subheader("Local services")
        _render_service_status(st, diagnostic)
        start_col, stop_col = st.columns(2)
        if start_col.button(
            "Start stack",
            use_container_width=True,
            disabled=diagnostic.wigolo_ready or diagnostic.state == "wrong_service",
        ):
            services.start()
            st.rerun()
        if stop_col.button(
            "Stop owned",
            use_container_width=True,
            disabled=not diagnostic.owned_process or controller.has_active_runs(),
        ):
            services.stop()
            st.rerun()
        if diagnostic.recent_output:
            with st.expander("Redacted startup details"):
                st.code("\n".join(diagnostic.recent_output[-12:]), language=None)
        st.divider()
        st.subheader("Provider status")
        if config_error:
            st.error("MiMo and Exa are not configured.")
            st.caption("Use Provider setup in the top navigation to save the required keys.")
        else:
            st.success("MiMo and Exa connected")
            fallback = "enabled" if os.environ.get("FIRECRAWL_API_KEY", "").strip() else "off"
            st.caption(f"Key values hidden · Firecrawl {fallback} · mimo-v2.5-pro")
        st.caption(
            "The local server must remain running during research. Cancellation is cooperative."
        )


def _render_history_page(st: object, controller: LiveResearchController, default_db: Path) -> None:
    st.markdown(
        """
        <section class="history-heading">
          <div class="hero-kicker">PERSISTED LOCALLY</div>
          <h1>Past research</h1>
          <p>Return to an earlier trail without starting the work again.</p>
        </section>
        """,
        unsafe_allow_html=True,
    )
    _render_history(st, controller, default_db)


def _render_start_form(
    st: object,
    controller: LiveResearchController,
    wigolo_ready: bool,
    config_error: str | None,
    default_db: Path,
) -> None:
    with st.form("mvp5-live-start", clear_on_submit=False):
        claim = st.text_area(
            "What do you want to look into?",
            height=136,
            placeholder="Type one clear public claim…",
            label_visibility="collapsed",
        )
        acknowledged = st.checkbox(
            "This is public and non-sensitive, and I’ll review what comes back."
        )
        submitted = st.form_submit_button(
            "Begin research",
            type="primary",
            use_container_width=True,
            disabled=bool(config_error) or not wigolo_ready,
        )
    if not submitted:
        if config_error:
            st.error("Providers are not configured. Use Provider setup to connect MiMo and Exa.")
        if not wigolo_ready:
            st.info("The local research service is not ready. Open Advanced to start it.")
        st.caption(
            "Human review is required before external or high-stakes use. "
            "A validated release is not a guarantee of factual infallibility."
        )
        return
    if not acknowledged:
        st.error(
            "Confirm that the claim is public/non-sensitive and that you will "
            "human-review the result before starting research."
        )
        return
    try:
        database = str(st.session_state.get("mlp2_database", str(default_db)))
        run_id_text = str(st.session_state.get("mlp2_run_id", ""))
        max_tokens = int(st.session_state.get("mlp2_max_tokens", 200_000))
        max_cost = str(st.session_state.get("mlp2_max_cost", "0.15"))
        max_calls = int(st.session_state.get("mlp2_max_calls", 160))
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
        :root {
          --mlp-ink: #111217;
          --mlp-muted: #6e7180;
          --mlp-line: #dddfe7;
          --mlp-paper: #f7f7f9;
          --mlp-white: #ffffff;
          --mlp-blue: #4776f3;
          --mlp-violet: #8067f2;
          --mlp-cyan: #42b8df;
          --mlp-shadow: 0 24px 70px rgba(33, 38, 60, .12);
        }
        .stApp {
          background:
            radial-gradient(circle at 14% 9%, rgba(102,128,244,.1), transparent 31rem),
            radial-gradient(circle at 89% 12%, rgba(135,100,241,.09), transparent 30rem),
            var(--mlp-paper);
          color: var(--mlp-ink);
        }
        .stApp::before {
          content: ""; position: fixed; inset: 0; z-index: 0; pointer-events: none;
          opacity: .2;
          background-image:
            linear-gradient(rgba(61,67,91,.08) 1px, transparent 1px),
            linear-gradient(90deg, rgba(61,67,91,.08) 1px, transparent 1px);
          background-size: 42px 42px;
          mask-image: linear-gradient(to bottom, black, transparent 68%);
        }
        .stApp > * { position: relative; z-index: 1; }
        .block-container { max-width: 1240px; padding: 1.35rem 2.4rem 4rem; }
        [data-testid="stHeader"], [data-testid="stToolbar"], .stDeployButton {
          background: transparent; visibility: hidden;
        }
        [data-testid="stSidebar"] { display: none; }
        .brand {
          background: linear-gradient(100deg, #111217, #37416e 55%, var(--mlp-violet));
          color: transparent; background-clip: text; -webkit-background-clip: text;
          font-size: 1.03rem; font-weight: 780;
          letter-spacing: -.035em; white-space: nowrap;
        }
        .local-pill {
          color: #50556a; background: rgba(255,255,255,.66); border: 1px solid #d9dce7;
          border-radius: 999px; display: table; margin: 0 auto; padding: .35rem .65rem;
          font-size: .62rem; font-weight: 750; letter-spacing: .15em; text-align: center;
        }
        h1, h2, h3 { color: var(--mlp-ink); letter-spacing: -.04em; overflow-wrap: anywhere; }
        .hero { padding: 6.4rem 0 2.2rem; text-align: center; }
        .st-key-mlp2_primary { max-width: 780px; margin: 0 auto; }
        .hero-kicker, .panel-eyebrow {
          color: #595f75; font-size: .69rem; font-weight: 780; letter-spacing: .16em;
          text-transform: uppercase;
        }
        .hero-kicker {
          display: table; margin: 0 auto; padding: .38rem .75rem; border-radius: 999px;
          background: rgba(255,255,255,.68); border: 1px solid #dcdeea;
          box-shadow: 0 8px 28px rgba(48,55,82,.06);
        }
        .hero h1 {
          margin: .7rem 0 1.25rem; font-size: clamp(3rem, 6.2vw, 5.4rem);
          font-weight: 620; line-height: .99; letter-spacing: -.065em;
          animation: mlp-rise .72s cubic-bezier(.2,.75,.25,1) both;
        }
        .hero h1 span {
          background: linear-gradient(100deg, var(--mlp-blue), var(--mlp-violet) 62%, #a15fdc);
          color: transparent; background-clip: text; -webkit-background-clip: text;
          background-size: 180% 100%; animation: mlp-gradient 5s ease-in-out infinite alternate;
        }
        .hero p, .history-heading p {
          max-width: 660px; margin: 0 auto; color: var(--mlp-muted);
          font-size: 1.02rem; line-height: 1.65;
        }
        .hero p { animation: mlp-rise .72s .1s cubic-bezier(.2,.75,.25,1) both; }
        .research-stage {
          position: relative; height: 250px; margin: 2.5rem auto .2rem; overflow: hidden;
          border: 1px solid rgba(141,147,177,.28); border-radius: 28px;
          background: linear-gradient(145deg, #151722, #1c2030 58%, #171925);
          box-shadow: 0 28px 70px rgba(23,27,45,.22);
          animation: mlp-stage-in .9s .18s cubic-bezier(.2,.8,.25,1) both;
          perspective: 900px;
        }
        .stage-grid {
          position: absolute; inset: -40%; transform: rotateX(64deg) translateY(22%);
          transform-origin: center bottom; opacity: .24;
          background-image:
            linear-gradient(rgba(117,134,236,.28) 1px, transparent 1px),
            linear-gradient(90deg, rgba(117,134,236,.28) 1px, transparent 1px);
          background-size: 34px 34px; animation: mlp-grid 7s linear infinite;
        }
        .stage-glow {
          position: absolute; width: 380px; height: 240px; left: 50%; top: 44%;
          transform: translate(-50%,-50%); border-radius: 50%; filter: blur(42px);
          background: radial-gradient(
            circle, rgba(75,113,244,.44), rgba(126,91,232,.16) 48%, transparent 72%
          );
          animation: mlp-pulse 3.2s ease-in-out infinite;
        }
        .stage-orbit {
          position: absolute; width: 168px; height: 168px; left: 50%; top: 50%;
          margin: -84px; border: 1px solid rgba(152,166,255,.22); border-radius: 50%;
          animation: mlp-spin 10s linear infinite;
        }
        .stage-orbit::before, .stage-orbit::after {
          content: ""; position: absolute; inset: 20px; border: 1px dashed rgba(154,132,248,.3);
          border-radius: 50%;
        }
        .stage-orbit::after { inset: -26px; border-style: solid; opacity: .32; }
        .stage-orbit span {
          position: absolute; width: 8px; height: 8px; border-radius: 50%;
          background: #7b9cff; box-shadow: 0 0 18px #7092ff;
        }
        .stage-orbit span:nth-child(1) { left: 17px; top: 19px; }
        .stage-orbit span:nth-child(2) { right: -4px; top: 73px; background: #a985ff; }
        .stage-orbit span:nth-child(3) { left: 56px; bottom: -3px; background: #61c9ee; }
        .signal-core {
          position: absolute; left: 50%; top: 50%; width: 58px; height: 58px;
          transform: translate(-50%,-50%); border: 1px solid rgba(255,255,255,.22);
          border-radius: 18px; display: grid; place-items: center; color: white;
          background: linear-gradient(145deg, rgba(109,139,255,.95), rgba(119,79,219,.95));
          box-shadow: 0 0 0 8px rgba(101,124,238,.1), 0 18px 38px rgba(48,54,132,.42);
          animation: mlp-core 2.4s ease-in-out infinite;
        }
        .signal-core b { font-size: 1.15rem; }
        .signal-core i {
          position: absolute; inset: -9px; border: 1px solid rgba(141,160,255,.42);
          border-radius: 24px; animation: mlp-ring 2.4s ease-out infinite;
        }
        .signal-card {
          position: absolute; width: 174px; padding: .85rem .9rem .75rem 1rem;
          text-align: left; color: #f7f8ff; border: 1px solid rgba(255,255,255,.13);
          border-radius: 15px; background: rgba(34,38,56,.74);
          box-shadow: 0 16px 36px rgba(5,7,16,.28); backdrop-filter: blur(14px);
        }
        .signal-card small { color: #989fbd; font-size: .56rem; letter-spacing: .14em; }
        .signal-card strong { display: block; margin: .22rem 0 .55rem; font-size: .78rem; }
        .signal-dot {
          position: absolute; width: 6px; height: 6px; right: 11px; top: 11px;
          border-radius: 50%; background: #6c91ff; box-shadow: 0 0 12px #6c91ff;
          animation: mlp-blink 1.7s ease-in-out infinite;
        }
        .signal-card em { display: flex; gap: 4px; height: 3px; }
        .signal-card em i { display: block; border-radius: 4px; background: #59617d; }
        .signal-card em i:nth-child(1) { width: 47%; }
        .signal-card em i:nth-child(2) { width: 28%; background: #707af0; }
        .signal-card em i:nth-child(3) { width: 15%; }
        .signal-support { left: 5%; top: 14%; animation: mlp-float-a 5s ease-in-out infinite; }
        .signal-oppose { right: 4%; top: 18%; animation: mlp-float-b 5.8s ease-in-out infinite; }
        .signal-citations {
          left: 10%; bottom: 10%; animation: mlp-float-b 6.2s -2s ease-in-out infinite;
        }
        .stage-scan {
          position: absolute; left: 0; right: 0; height: 1px; top: 0;
          background: linear-gradient(90deg, transparent, rgba(117,157,255,.7), transparent);
          box-shadow: 0 0 16px rgba(90,132,255,.5); animation: mlp-scan 4.6s linear infinite;
        }
        .history-heading { padding: 5rem 0 2rem; text-align: center; }
        .history-heading h1 { margin: .55rem 0 .8rem; font-size: clamp(2.8rem, 5vw, 4.4rem); }
        [data-testid="stForm"], [data-testid="stVerticalBlockBorderWrapper"] {
          background: rgba(255,255,255,.88); border: 1px solid rgba(141,147,177,.3) !important;
          border-radius: 24px !important; box-shadow: var(--mlp-shadow);
          backdrop-filter: blur(18px);
        }
        [data-testid="stForm"] {
          padding: 1.25rem 1.35rem .95rem;
          animation: mlp-rise .7s .24s cubic-bezier(.2,.75,.25,1) both;
        }
        [data-testid="stTextArea"] textarea {
          background: transparent; border: 0; box-shadow: none; color: var(--mlp-ink);
          font-size: 1.1rem; line-height: 1.55; resize: none;
        }
        [data-testid="stTextArea"] textarea:focus { box-shadow: none; }
        [data-testid="stTextInput"] input, [data-testid="stNumberInput"] input {
          border-color: var(--mlp-line); border-radius: 11px;
          transition: border-color .18s ease, box-shadow .18s ease, transform .18s ease;
        }
        [data-testid="stTextInput"] input:focus, [data-testid="stNumberInput"] input:focus {
          border-color: var(--mlp-blue); box-shadow: 0 0 0 3px rgba(71,118,243,.11);
          transform: translateY(-1px);
        }
        [data-testid="stMetric"] {
          background: linear-gradient(140deg, rgba(255,255,255,.96), rgba(241,243,251,.92));
          border: 1px solid rgba(141,147,177,.26);
          padding: .75rem 1rem; border-radius: 14px;
        }
        [data-testid="stCheckbox"] input { accent-color: var(--mlp-blue); }
        .stButton > button, .stFormSubmitButton > button {
          border-color: #d0d2dc; border-radius: 999px; min-height: 2.45rem;
          background: rgba(255,255,255,.76); color: #2d3040; font-weight: 620;
          transition: transform .16s ease, box-shadow .2s ease, background .2s ease,
            border-color .2s ease;
        }
        .stButton > button:hover {
          border-color: #aeb8ec; background: rgba(242,244,255,.94); color: #323a76;
          transform: translateY(-3px) scale(1.01); box-shadow: 0 12px 25px rgba(52,61,111,.14);
        }
        .stButton > button:active, .stFormSubmitButton > button:active {
          transform: translateY(1px) scale(.975); transition-duration: .06s;
        }
        .stButton > button[kind="primary"], .stFormSubmitButton > button[kind="primary"] {
          background: linear-gradient(100deg, #405feb, #6d61ef 58%, #8e56da);
          background-size: 180% 100%; animation: mlp-button-flow 4s ease-in-out infinite alternate;
          border-color: transparent; color: white; box-shadow: 0 11px 28px rgba(77,78,191,.27);
          border-radius: 999px; font-weight: 700;
        }
        .stAlert { border-radius: 14px; }
        [data-baseweb="notification"] { border-left-color: var(--mlp-blue) !important; }
        [role="dialog"] { border-radius: 24px; }
        [role="dialog"] { animation: mlp-pop .26s cubic-bezier(.2,.8,.25,1) both; }
        hr { border-color: var(--mlp-line); }
        @keyframes mlp-rise {
          from { opacity: 0; transform: translateY(16px); }
          to { opacity: 1; transform: translateY(0); }
        }
        @keyframes mlp-pop {
          from { opacity: 0; transform: translateY(8px) scale(.985); }
          to { opacity: 1; transform: translateY(0) scale(1); }
        }
        @keyframes mlp-stage-in {
          from { opacity: 0; transform: translateY(24px) scale(.97); }
          to { opacity: 1; transform: translateY(0) scale(1); }
        }
        @keyframes mlp-gradient { to { background-position: 100% 50%; } }
        @keyframes mlp-button-flow { to { background-position: 100% 50%; } }
        @keyframes mlp-grid {
          from { background-position: 0 0, 0 0; }
          to { background-position: 0 34px, 34px 0; }
        }
        @keyframes mlp-spin { to { transform: rotate(360deg); } }
        @keyframes mlp-pulse {
          0%, 100% { opacity: .7; transform: translate(-50%,-50%) scale(.9); }
          50% { opacity: 1; transform: translate(-50%,-50%) scale(1.14); }
        }
        @keyframes mlp-core {
          0%, 100% { transform: translate(-50%,-50%) rotate(-2deg) scale(.98); }
          50% { transform: translate(-50%,-50%) rotate(2deg) scale(1.05); }
        }
        @keyframes mlp-ring {
          0% { opacity: .8; transform: scale(.8); }
          70%, 100% { opacity: 0; transform: scale(1.35); }
        }
        @keyframes mlp-blink { 50% { opacity: .35; transform: scale(.72); } }
        @keyframes mlp-float-a {
          0%, 100% { transform: translate3d(0,0,0) rotate(-1deg); }
          50% { transform: translate3d(7px,-8px,0) rotate(1deg); }
        }
        @keyframes mlp-float-b {
          0%, 100% { transform: translate3d(0,0,0) rotate(1deg); }
          50% { transform: translate3d(-8px,7px,0) rotate(-1deg); }
        }
        @keyframes mlp-scan {
          0% { transform: translateY(-8px); opacity: 0; }
          12%, 82% { opacity: 1; }
          100% { transform: translateY(260px); opacity: 0; }
        }
        @media (max-width: 760px) {
          .block-container { padding: .85rem 1rem 3rem; }
          .local-pill { display: none; }
          [data-testid="stHorizontalBlock"]:has(.brand) {
            display: grid !important; grid-template-columns: repeat(3, 1fr); gap: .55rem;
          }
          [data-testid="stHorizontalBlock"]:has(.brand) > [data-testid="stColumn"] {
            width: auto !important; min-width: 0 !important; flex: none !important;
          }
          [data-testid="stHorizontalBlock"]:has(.brand) > [data-testid="stColumn"]:first-child {
            grid-column: 1 / -1; margin-bottom: .15rem;
          }
          [data-testid="stHorizontalBlock"]:has(.brand) > [data-testid="stColumn"]:nth-child(2) {
            display: none;
          }
          [data-testid="stHorizontalBlock"]:has(.brand) .stButton > button {
            width: 100%; padding-left: .4rem; padding-right: .4rem; font-size: .82rem;
          }
          .hero { padding: 3.7rem 0 1.6rem; }
          .hero h1 { font-size: clamp(2.75rem, 14vw, 4.2rem); }
          .hero p { font-size: .95rem; }
          .research-stage { height: 255px; margin-top: 1.8rem; border-radius: 22px; }
          .signal-card { width: 142px; padding: .68rem .7rem .62rem .78rem; }
          .signal-card strong { font-size: .68rem; }
          .signal-support { left: 3%; top: 7%; }
          .signal-oppose { right: 2%; top: 11%; }
          .signal-citations { left: 4%; bottom: 6%; }
          [data-testid="stHorizontalBlock"] { gap: .55rem; }
        }
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
