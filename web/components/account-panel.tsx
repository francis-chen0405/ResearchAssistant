"use client";

import { useEffect, useState } from "react";
import type { AuthenticatedUser, CredentialMetadata, HostedSettings } from "@/lib/hosted-api";

type Props = { user: AuthenticatedUser | null; credentials: CredentialMetadata[]; settings: HostedSettings; open: boolean; onClose: () => void; onSave: (values: Record<string, string>) => Promise<void>; onSaveSettings: (settings: HostedSettings) => Promise<void>; onClear: (name: string) => Promise<void>; onSignOut: () => Promise<void> };

export function AccountPanel({ user, credentials, settings, open, onClose, onSave, onSaveSettings, onClear, onSignOut }: Props): React.ReactElement | null {
  const [values, setValues] = useState<Record<string, string>>({});
  const [workspace, setWorkspace] = useState(settings);
  const [saving, setSaving] = useState(false);
  useEffect(() => {
    if (!open) return;
    const timer = window.setTimeout(() => setWorkspace(settings), 0);
    return () => window.clearTimeout(timer);
  }, [open, settings]);
  if (!open) return null;
  const save = async () => { setSaving(true); try { await onSave(values); setValues({}); } finally { setSaving(false); } };
  return <div className="panel-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}><aside className="side-panel" aria-label="Account and providers"><button className="close-button" type="button" onClick={onClose} aria-label="Close account">×</button><p className="eyebrow">Personal account</p><h2>{user?.email ?? "Your workspace"}</h2><p className="muted">Your runs and provider connections are isolated to this account.</p><p className="eyebrow section-label">Workspace defaults</p><div className="control-stack"><label>Display name<input value={workspace.display_name ?? ""} onChange={(event) => setWorkspace({ ...workspace, display_name: event.target.value || null })} /></label><label>Model calls<input type="number" min={1} max={160} value={workspace.default_max_llm_calls} onChange={(event) => setWorkspace({ ...workspace, default_max_llm_calls: Number(event.target.value) })} /></label><label>Token ceiling<input type="number" min={1} max={500000} value={workspace.default_max_tokens} onChange={(event) => setWorkspace({ ...workspace, default_max_tokens: Number(event.target.value) })} /></label><label>Cost ceiling<input type="number" min={0.01} max={1} step={0.01} value={workspace.default_max_cost_usd} onChange={(event) => setWorkspace({ ...workspace, default_max_cost_usd: event.target.value })} /></label></div><button type="button" className="quiet-button full" onClick={() => void onSaveSettings(workspace)}>Save workspace defaults</button><p className="eyebrow section-label">Provider connections</p><div className="credential-list">{credentials.map((credential) => <label key={credential.name}>{credential.name.replaceAll("_", " ")}<span className={credential.configured ? "configured" : "not-configured"}>{credential.configured ? "configured" : "not configured"}</span><input type="password" autoComplete="new-password" value={values[credential.name] ?? ""} onChange={(event) => setValues({ ...values, [credential.name]: event.target.value })} placeholder={credential.configured ? "Replace securely" : "Add securely"} />{credential.configured ? <button className="inline-link" type="button" onClick={() => void onClear(credential.name)}>Remove connection</button> : null}</label>)}</div><button type="button" className="primary-button full" onClick={() => void save()} disabled={saving}>{saving ? "Saving…" : "Save connections"}<span>→</span></button><button type="button" className="quiet-button full" onClick={() => void onSignOut()}>Sign out</button></aside></div>;
}
