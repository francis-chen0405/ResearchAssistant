"use client";
import { FormEvent, useEffect, useState } from "react";
import { Configuration, ModelProfile, ProviderSelection, researchApi } from "@/lib/api";
import { Dialog } from "./dialog";
import { StatusPill } from "./workspace";

const providers = [
  { id: "mimo", field: "mimo_api_key", vault: "MIMO_API_KEY", name: "Xiaomi MiMo", description: "Finds, selects and extracts research. Required." },
  { id: "openai", field: "luna_api_key", vault: "LUNA_API_KEY", name: "OpenAI", description: "Luna High checks gaps and analyzes evidence. Required." },
  { id: "serpsearch", field: "serpsearch_api_key", vault: "SERPSEARCH_API_KEY", name: "SERP Search", description: "Web search. Required when selected." },
  { id: "exa", field: "exa_api_key", vault: "EXA_API_KEY", name: "Exa", description: "Search by meaning. Required when selected." },
  { id: "openalex", field: "openalex_api_key", vault: "OPENALEX_API_KEY", name: "OpenAlex", description: "Scholarly literature. Required when selected." },
  { id: "pubmed", field: "pubmed_api_key", vault: "PUBMED_API_KEY", name: "PubMed", description: "Optional key for a higher request allowance." },
  { id: "firecrawl", field: "firecrawl_api_key", vault: "FIRECRAWL_API_KEY", name: "Firecrawl", description: "Optional source-reading fallback." },
] as const;

export function ProviderSetup({ configuration, selectedProviders, onClose, onSaved }: { configuration: Configuration | null; selectedProviders: ProviderSelection; onClose: () => void; onSaved: (message: string) => Promise<void> }) {
  const [keys, setKeys] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [checks, setChecks] = useState<Record<string, string>>({});
  const [profiles, setProfiles] = useState<ModelProfile[]>([]);
  useEffect(() => { void researchApi.profiles().then(setProfiles).catch(() => setMessage("Model profiles could not be loaded. Reopen settings to retry.")); }, []);
  const submit = async (event: FormEvent) => {
    event.preventDefault(); setBusy(true); setMessage(null);
    try {
      const payload = Object.fromEntries(Object.entries(keys).filter(([, value]) => value.trim()));
      const result = await researchApi.saveCredentials(payload, selectedProviders);
      setKeys({}); setChecks({}); await onSaved("Keys saved securely. Settings apply to future runs."); setMessage(result.saved ? "Saved securely. You can now check access or begin research." : result.message);
    } catch (error) { setMessage(error instanceof Error ? error.message : "Keys could not be saved."); }
    finally { setKeys({}); setBusy(false); }
  };
  const check = async (id: string) => {
    setBusy(true);
    try { const result = await researchApi.checkConnection(id); setChecks(current => ({ ...current, [id]: result.message })); }
    catch { setChecks(current => ({ ...current, [id]: "Could not check access. Try again." })); }
    finally { setBusy(false); }
  };
  const remove = async (vault: string, id: string) => {
    setBusy(true);
    try { await researchApi.removeCredential(vault); setChecks(current => ({ ...current, [id]: "Key removed." })); setKeys({}); await onSaved("Provider key removed."); }
    catch { setMessage("Key could not be removed. Wait for active research to finish and retry."); }
    finally { setBusy(false); }
  };
  return <Dialog title="Connect your research tools" onClose={onClose} wide><p className="modal-intro">Bring your provider accounts. Your keys stay in macOS Keychain or Windows Credential Manager. Your research and settings stay on this device.</p><aside className="keychain-help"><strong>About the macOS password prompt</strong><p>If macOS asks to access your login keychain, it needs your Mac login/keychain password. Enter provider API keys only in the fields below. A rebuilt unsigned app may ask for access again after an update.</p></aside><div className="onboarding-steps"><span><b>01</b> Connect MiMo + OpenAI</span><span><b>02</b> Choose sources in Settings</span><span><b>03</b> Start a question</span></div><form className="connections-form" onSubmit={submit}><div className="connection-grid">{providers.map(provider => { const saved = configuration?.saved_credentials.includes(provider.id); return <section className="connection-card" key={provider.id}><div className="connection-heading"><h3>{provider.name}</h3><StatusPill tone={saved ? "support" : "neutral"}>{saved ? "Key saved" : "Not connected"}</StatusPill></div><p>{provider.description}</p><label>{provider.name} API key<input type="password" autoComplete="off" spellCheck={false} value={keys[provider.field] || ""} placeholder={saved ? "Enter a key to replace the saved key" : "Paste your API key"} onChange={event => setKeys(current => ({ ...current, [provider.field]: event.target.value }))} /></label><div className="connection-actions"><button type="button" disabled={busy || !saved} onClick={() => void check(provider.id)}>{provider.id === "mimo" || provider.id === "openai" ? "Check connection" : "Check key status"}</button><button type="button" disabled={busy || !saved} onClick={() => void remove(provider.vault, provider.id)}>Remove key</button></div>{checks[provider.id] && <p className="connection-feedback" role="status">{checks[provider.id]}</p>}</section>; })}</div><p className="security-note">Connection checks for MiMo and OpenAI only list models; they do not generate text. Saved source keys are checked during research. arXiv requires no key; PubMed can also work without one.</p>{message && <p className="setup-status" role="status">{message}</p>}<button className="primary-action" type="submit" disabled={busy || !Object.values(keys).some(value => value.trim())}>{busy ? "Working…" : "Save keys securely"} <span aria-hidden="true">↗</span></button></form><section className="profile-settings"><p className="eyebrow">Models are separate from connections</p><h3>One carefully configured research team.</h3><p>A key connects your account. The Standard research profile selects the models and budget caps used by each research role. Existing runs keep their original configuration.</p>{profiles.map(profile => <details key={profile.id}><summary>{profile.name} · roles and budget caps</summary><p>{profile.description}. Price caps reviewed {profile.pricing_reviewed}; these are conservative reservations, not a billing estimate.</p><div className="profile-table">{profile.models.map(model => <article key={model.model}><strong>{model.model}</strong><p>{model.roles}</p><small>${model.input_per_million} input / ${model.output_per_million} output per million tokens · {model.completion_limit.toLocaleString()} output tokens per call</small></article>)}</div></details>)}<details><summary>Restore standard model routing</summary><p>Only use this if an earlier custom deployment prevents setup. Restores the standard OpenAI endpoint and Luna model for future research; saved keys and history are retained.</p><button type="button" disabled={busy} onClick={async () => { setBusy(true); try { await researchApi.saveCredentials({ luna_base_url: "https://api.openai.com/v1", luna_model: "gpt-5.6-luna" }, selectedProviders); await onSaved("Standard model routing restored."); setMessage("Standard model routing restored."); } catch { setMessage("Routing could not be restored. Wait for active research to finish."); } finally { setBusy(false); } }}>Restore standard route</button></details></section></Dialog>;
}
