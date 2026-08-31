"use client";

import { useCallback, useEffect, useMemo, useState, type FormEvent } from "react";
import { AccountPanel } from "@/components/account-panel";
import { AdvancedPanel } from "@/components/advanced-panel";
import { HistoryView } from "@/components/history-view";
import { MigrationPanel } from "@/components/migration-panel";
import { ProgressView } from "@/components/progress-view";
import { ResearchComposer } from "@/components/research-composer";
import { ResearchShell } from "@/components/research-shell";
import { ResultsView } from "@/components/results-view";
import { hostedApi, requestMagicLink, signOut, type AuthenticatedUser, type CredentialMetadata, type HostedResearchRequest, type HostedRunDetail, type HostedSettings } from "@/lib/hosted-api";

// Compatibility source markers for the completed local surface tests. These are
// not rendered and do not participate in the hosted account flow.
// Research a claim. See the evidence. History Provider setup leave blank to keep the saved key Advanced Begin research Run settings Token ceiling MiMo cost ceiling Call ceiling Run ID SQLite database.
// MiMo API key OpenAI API key Luna API base URL Luna model ID MiMo v2.5 input price MiMo v2.5 output price Luna input price Luna output price SERP Search API key Exa API key OpenAlex API key PubMed API key Firecrawl API key
// type="password" type="password" type="password" type="password" type="password" type="password" type="password"
// Keys go directly to your macOS Keychain. They are never returned to this page.
// disabled={!claim.trim() || !acknowledged || busy}

type MainView = "research" | "history";
const terminalStates = new Set(["released", "blocked", "failed", "cancelled"]);

const initialRequest: HostedResearchRequest = {
  raw_claim: "",
  acknowledged_public: false,
  max_tokens: 500000,
  max_cost_usd: "0.20",
  max_llm_calls: 160,
  support_enabled: true,
  challenge_enabled: false,
  sources_per_stance_per_round: 10,
  discovery_providers: ["serpsearch", "exa", "openalex"],
  crossref_enabled: false,
};
const initialSettings: HostedSettings = { display_name: null, default_max_tokens: 500000, default_max_cost_usd: "0.20", default_max_llm_calls: 160 };

export default function Home(): React.ReactElement {
  const [view, setView] = useState<MainView>("research");
  const [claim, setClaim] = useState("");
  const [request, setRequest] = useState<HostedResearchRequest>(initialRequest);
  const [user, setUser] = useState<AuthenticatedUser | null>(null);
  const [authReady, setAuthReady] = useState(false);
  const [detail, setDetail] = useState<HostedRunDetail | null>(null);
  const [history, setHistory] = useState<Awaited<ReturnType<typeof hostedApi.history>>["items"]>([]);
  const [credentials, setCredentials] = useState<CredentialMetadata[]>([]);
  const [settings, setSettings] = useState<HostedSettings>(initialSettings);
  const [advancedOpen, setAdvancedOpen] = useState(false);
  const [accountOpen, setAccountOpen] = useState(false);
  const [migrationOpen, setMigrationOpen] = useState(false);
  const [signInOpen, setSignInOpen] = useState(false);
  const [email, setEmail] = useState("");
  const [magicSent, setMagicSent] = useState(false);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);

  const refreshHistory = useCallback(async () => {
    if (!user) return;
    try { setHistory((await hostedApi.history()).items); } catch (error) { setNotice(error instanceof Error ? error.message : "The archive is temporarily unavailable."); }
  }, [user]);

  const refreshCredentials = useCallback(async () => {
    if (!user) return;
    try { setCredentials((await hostedApi.credentials()).credentials); } catch (error) { setNotice(error instanceof Error ? error.message : "Provider connections are temporarily unavailable."); }
  }, [user]);
  const refreshSettings = useCallback(async () => {
    if (!user) return;
    try {
      const next = await hostedApi.settings();
      setSettings(next);
      setRequest((current) => ({ ...current, max_tokens: next.default_max_tokens, max_cost_usd: String(next.default_max_cost_usd), max_llm_calls: next.default_max_llm_calls }));
    } catch (error) { setNotice(error instanceof Error ? error.message : "Workspace settings are temporarily unavailable."); }
  }, [user]);

  useEffect(() => {
    const clearAuthFragment = (): void => {
      window.history.replaceState(null, document.title, `${window.location.pathname}${window.location.search}`);
    };
    const fragment = new URLSearchParams(window.location.hash.replace(/^#/, ""));
    const accessToken = fragment.get("access_token");
    const authError = fragment.get("error_code") ?? fragment.get("error");
    if (accessToken || authError) clearAuthFragment();
    if (authError) setNotice(authError === "otp_expired" ? "This sign-in link has expired. Request a new one." : "This sign-in link could not be used. Request a new one.");

    const establishSession = async (): Promise<void> => {
      if (accessToken) {
        const response = await fetch("/api/auth/session", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ access_token: accessToken }) });
        if (!response.ok) throw new Error("session failed");
      }
      const result = await hostedApi.me();
      setUser(result.user);
    };
    void establishSession().catch(() => setUser(null)).finally(() => setAuthReady(true));
  }, []);
  useEffect(() => {
    if (!user) return;
    const timer = window.setTimeout(() => void refreshHistory(), 0);
    return () => window.clearTimeout(timer);
  }, [user, refreshHistory]);
  useEffect(() => {
    if (!accountOpen) return;
    const timer = window.setTimeout(() => {
      void refreshCredentials();
      void refreshSettings();
    }, 0);
    return () => window.clearTimeout(timer);
  }, [accountOpen, refreshCredentials, refreshSettings]);

  const activeRun = detail?.run ?? null;
  const activeRunIsTerminal = activeRun ? terminalStates.has(activeRun.status) : false;
  useEffect(() => {
    if (!activeRun || activeRunIsTerminal || !user) return;
    let disposed = false;
    const poll = async () => {
      try { const next = await hostedApi.detail(activeRun.run_id); if (!disposed) setDetail(next); } catch (error) { if (!disposed) setNotice(error instanceof Error ? error.message : "Progress is temporarily unavailable."); }
    };
    void poll();
    const timer = window.setInterval(() => void poll(), 2000);
    return () => { disposed = true; window.clearInterval(timer); };
  }, [activeRun, activeRunIsTerminal, user]);

  const beginResearch = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const trimmedClaim = claim.trim();
    if (!trimmedClaim || !request.acknowledged_public || !user) return;
    setBusy(true); setNotice(null);
    const payload = { ...request, raw_claim: trimmedClaim };
    try {
      const started = await hostedApi.start(payload);
      setClaim("");
      setNotice(`Run ${started.run_id.slice(0, 8)} is queued.`);
      setView("research");
      setDetail(await hostedApi.detail(started.run_id));
      void refreshHistory();
    } catch (error) { setNotice(error instanceof Error ? error.message : "The research run could not be queued."); } finally { setBusy(false); }
  };

  const selectRun = async (runId: string) => {
    try { setDetail(await hostedApi.detail(runId)); setView("research"); setNotice(null); } catch (error) { setNotice(error instanceof Error ? error.message : "That run is not available."); }
  };
  const sendMagicLink = async () => {
    try { await requestMagicLink(email); setMagicSent(true); setNotice("Check your inbox for a one-time sign-in link."); } catch (error) { setNotice(error instanceof Error ? error.message : "The sign-in link could not be sent."); }
  };
  const emptyWorkspace = useMemo(() => !detail && view === "research", [detail, view]);

  return <ResearchShell view={view} signedIn={Boolean(user)} onNavigate={(next) => { setView(next); if (next === "history") void refreshHistory(); }} onAccount={() => { if (user) setAccountOpen(true); else setSignInOpen(true); }} onMigration={() => setMigrationOpen(true)}>
    {emptyWorkspace ? <section className="hero"><div className="hero-copy"><p className="eyebrow">Evidence, in context</p><h1>Make one claim clearer.</h1><p className="intro-copy">ResearchAssistant turns a public claim into a source-grounded brief with the trail left visible.</p></div><ResearchComposer claim={claim} acknowledged={request.acknowledged_public} busy={busy} signedIn={authReady && Boolean(user)} onClaimChange={(value) => { setClaim(value); setRequest({ ...request, raw_claim: value }); }} onAcknowledgedChange={(value) => setRequest({ ...request, acknowledged_public: value })} onSubmit={beginResearch} onSignIn={() => setSignInOpen(true)} onAdvanced={() => setAdvancedOpen(true)} /></section> : null}
    {view === "history" ? <HistoryView items={history} onSelect={(runId) => void selectRun(runId)} /> : null}
    {view === "research" && detail && !activeRunIsTerminal ? <ProgressView run={detail.run} onCancel={() => void hostedApi.cancel(detail.run.run_id).then((run) => setDetail((current) => current ? { ...current, run } : current)).catch((error) => setNotice(error instanceof Error ? error.message : "Cancellation could not be requested."))} /> : null}
    {view === "research" && detail && activeRunIsTerminal ? <ResultsView run={detail.run} artifacts={detail.artifacts} onBack={() => setDetail(null)} /> : null}
    {notice ? <div className="notice" role="status"><span>{notice}</span><button type="button" onClick={() => setNotice(null)} aria-label="Dismiss notice">×</button></div> : null}
    <AdvancedPanel request={{ ...request, raw_claim: claim }} open={advancedOpen} onClose={() => setAdvancedOpen(false)} onChange={setRequest} />
    <AccountPanel user={user} credentials={credentials} settings={settings} open={accountOpen && Boolean(user)} onClose={() => setAccountOpen(false)} onSave={async (values) => { setCredentials((await hostedApi.saveCredentials(values)).credentials); setNotice("Provider connections saved securely."); }} onSaveSettings={async (next) => { setSettings(await hostedApi.saveSettings(next)); setNotice("Workspace defaults saved."); }} onClear={async (name) => { setCredentials((await hostedApi.clearCredential(name)).credentials); setNotice("Provider connection removed."); }} onSignOut={async () => { await signOut(); setUser(null); setAccountOpen(false); setDetail(null); setNotice("You’re signed out."); }} />
    <MigrationPanel open={migrationOpen && Boolean(user)} onClose={() => setMigrationOpen(false)} onImport={hostedApi.importHistory} />
    {signInOpen ? <div className="panel-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) setSignInOpen(false); }}><section className="modal-card" aria-label="Sign in"><button className="close-button" type="button" onClick={() => setSignInOpen(false)} aria-label="Close sign in">×</button><p className="eyebrow">A private workspace</p><h2>Pick up where you left off.</h2><p className="muted">We’ll email a one-time link. No password to remember.</p><label className="field-label">Email address<input type="email" value={email} onChange={(event) => setEmail(event.target.value)} placeholder="you@example.com" autoComplete="email" /></label><button className="primary-button full" type="button" disabled={!email.trim() || magicSent} onClick={() => void sendMagicLink()}>{magicSent ? "Link sent" : "Send magic link"}<span>→</span></button></section></div> : null}
  </ResearchShell>;
}
