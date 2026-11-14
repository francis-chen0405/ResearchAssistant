"use client";
import { FormEvent, useEffect, useRef, useState } from "react";
import {
  Configuration,
  ProviderSelection,
  StageModels,
  researchApi,
} from "@/lib/api";
import type { Settings } from "@/features/preferences/settings";
import { StatusPill } from "./workspace";

type ToggleKey = "useSerpSearch" | "useExa" | "useOpenAlex" | "useArxiv" | "usePubmed" | "useBrave" | "useSerper";
type ProviderRow = {
  id: string;
  field?: string;
  vault?: string;
  name: string;
  description: string;
  toggle?: ToggleKey;
  limit?: readonly [string, number];
  keyOptional?: boolean;
};

const groups: { title: string; note: string; rows: ProviderRow[] }[] = [
  {
    title: "Model providers",
    note: "Keys for the models chosen under Models. Only the providers your chosen models use are required.",
    rows: [
      { id: "mimo", field: "mimo_api_key", vault: "MIMO_API_KEY", name: "Xiaomi MiMo", description: "Finds, selects and extracts research." },
      { id: "openai", field: "luna_api_key", vault: "LUNA_API_KEY", name: "OpenAI", description: "Provides the selected GPT models." },
    ],
  },
  {
    title: "Web search",
    note: "General web results, official pages and news.",
    rows: [
      { id: "serpsearch", field: "serpsearch_api_key", vault: "SERPSEARCH_API_KEY", name: "SERP Search", description: "Google results for official pages, local documents and recent news.", toggle: "useSerpSearch", limit: ["serpsearch", 12] },
      { id: "brave", field: "brave_api_key", vault: "BRAVE_API_KEY", name: "Brave Search", description: "An independent web index for extra coverage.", toggle: "useBrave", limit: ["brave", 6] },
      { id: "serper", field: "serper_api_key", vault: "SERPER_API_KEY", name: "Serper", description: "Google results; use instead of SERP Search to limit overlap.", toggle: "useSerper", limit: ["serper", 6] },
      { id: "exa", field: "exa_api_key", vault: "EXA_API_KEY", name: "Exa", description: "Finds relevant pages even when they use different wording.", toggle: "useExa", limit: ["exa", 18] },
    ],
  },
  {
    title: "Scholarly search",
    note: "Academic papers and preprints.",
    rows: [
      { id: "openalex", field: "openalex_api_key", vault: "OPENALEX_API_KEY", name: "OpenAlex", description: "Academic papers across disciplines.", toggle: "useOpenAlex", limit: ["openalex", 10] },
      { id: "arxiv", name: "arXiv", description: "Preprints in computing, maths and physics. No key needed.", toggle: "useArxiv", limit: ["arxiv", 6] },
      { id: "pubmed", field: "pubmed_api_key", vault: "PUBMED_API_KEY", name: "PubMed", description: "Biomedical and public-health literature. A key is optional and raises the request limit.", toggle: "usePubmed", limit: ["pubmed", 6], keyOptional: true },
    ],
  },
  {
    title: "Reading fallback",
    note: "Used only when a page cannot be read directly.",
    rows: [
      { id: "firecrawl", field: "firecrawl_api_key", vault: "FIRECRAWL_API_KEY", name: "Firecrawl", description: "Optional fallback for pages the built-in reader cannot open.", keyOptional: true },
    ],
  },
];

type ConnectionChecks = {
  stageModelsKey: string;
  messages: Record<string, string>;
};

export function ProviderSetup({
  configuration,
  selectedProviders,
  stageModels,
  onSaved,
  settings,
  onSettings,
  locked = false,
}: {
  configuration: Configuration | null;
  selectedProviders: ProviderSelection;
  stageModels: StageModels;
  onClose?: () => void;
  onSaved: (message: string) => Promise<void>;
  /** Search-provider toggles and request limits share each provider's row. */
  settings?: Settings;
  onSettings?: (settings: Settings) => void;
  locked?: boolean;
}) {
  const [keys, setKeys] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const actionPending = useRef(false);
  const [message, setMessage] = useState<string | null>(null);
  const [checks, setChecks] = useState<ConnectionChecks>({
    stageModelsKey: "",
    messages: {},
  });
  const stageModelsKey = JSON.stringify(stageModels);
  const currentStageModelsKey = useRef(stageModelsKey);
  const currentChecks =
    checks.stageModelsKey === stageModelsKey ? checks.messages : {};
  const usesMiMo = Object.values(stageModels).some((choice) =>
    choice.startsWith("mimo-"),
  );
  const usesOpenAI = Object.values(stageModels).some((choice) =>
    choice.startsWith("gpt-"),
  );
  useEffect(() => {
    currentStageModelsKey.current = stageModelsKey;
  }, [stageModelsKey]);
  const beginAction = () => {
    if (actionPending.current) return false;
    actionPending.current = true;
    setBusy(true);
    return true;
  };
  const endAction = () => {
    actionPending.current = false;
    setBusy(false);
  };
  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (!beginAction()) return;
    setMessage(null);
    try {
      const payload = Object.fromEntries(
        Object.entries(keys).filter(([, value]) => value.trim()),
      );
      const result = await researchApi.saveCredentials(
        payload,
        stageModels,
        selectedProviders,
      );
      setKeys({});
      setChecks({ stageModelsKey, messages: {} });
      await onSaved("Keys saved securely. Settings apply to future runs.");
      setMessage(
        result.saved
          ? "Saved securely. You can now check access or begin research."
          : result.message,
      );
    } catch (error) {
      setMessage(
        error instanceof Error ? error.message : "Keys could not be saved.",
      );
    } finally {
      setKeys({});
      endAction();
    }
  };
  const check = async (id: string) => {
    if (!beginAction()) return;
    const checkedStageModelsKey = stageModelsKey;
    try {
      const result = await researchApi.checkConnection(id, stageModels);
      if (currentStageModelsKey.current === checkedStageModelsKey)
        setChecks((current) => ({
          stageModelsKey: checkedStageModelsKey,
          messages: {
            ...(current.stageModelsKey === checkedStageModelsKey
              ? current.messages
              : {}),
            [id]: result.message,
          },
        }));
    } catch {
      if (currentStageModelsKey.current === checkedStageModelsKey)
        setChecks((current) => ({
          stageModelsKey: checkedStageModelsKey,
          messages: {
            ...(current.stageModelsKey === checkedStageModelsKey
              ? current.messages
              : {}),
            [id]: "Could not check access. Try again.",
          },
        }));
    } finally {
      endAction();
    }
  };
  const remove = async (vault: string, id: string) => {
    if (!beginAction()) return;
    try {
      await researchApi.removeCredential(vault);
      setChecks((current) => ({
        stageModelsKey,
        messages: {
          ...(current.stageModelsKey === stageModelsKey
            ? current.messages
            : {}),
          [id]: "Key removed.",
        },
      }));
      setKeys({});
      await onSaved("Provider key removed.");
    } catch {
      setMessage(
        "Key could not be removed. Wait for active research to finish and retry.",
      );
    } finally {
      endAction();
    }
  };
  const restoreStandardRoute = async () => {
    if (!beginAction()) return;
    setMessage(null);
    try {
      await researchApi.saveCredentials(
        {
          luna_base_url: "https://api.openai.com/v1",
          luna_model: "gpt-5.6-luna",
        },
        stageModels,
        selectedProviders,
      );
      await onSaved("Standard model routing restored.");
      setMessage(
        "Standard model routing restored. Your per-role model choices remain unchanged.",
      );
    } catch {
      setMessage(
        "Routing could not be restored. Wait for active research to finish and retry.",
      );
    } finally {
      endAction();
    }
  };
  const providerDescriptions: Record<string, string> = {
    mimo: usesMiMo
      ? "Required by the selected MiMo research roles."
      : "Optional until a research role uses a MiMo model.",
    openai: usesOpenAI
      ? "Required by the selected GPT research roles."
      : "Optional until a research role uses a GPT model.",
  };
  const enabledCount = settings
    ? groups.flatMap((group) => group.rows).filter((row) => row.toggle && settings[row.toggle]).length
    : 0;
  const required: Record<string, boolean> = { mimo: usesMiMo, openai: usesOpenAI };
  const toggle = (row: ProviderRow) => {
    if (!settings || !onSettings || !row.toggle) return;
    if (row.toggle === "useOpenAlex" && settings.useOpenAlex && settings.scholarlySearchMode === "semantic") {
      onSettings({ ...settings, useOpenAlex: false, scholarlySearchMode: "lexical" });
    } else {
      onSettings({ ...settings, [row.toggle]: !settings[row.toggle] });
    }
  };
  return (
    <div className="provider-settings">
      <form className="connections-form" onSubmit={submit}>
        {groups.map((group) => (
          <fieldset className="provider-group" key={group.title}>
            <legend>{group.title}</legend>
            <p className="subtle">{group.note}</p>
            {group.rows.map((row) => {
              const saved = Boolean(configuration?.saved_credentials.includes(row.id));
              const enabled = row.toggle ? Boolean(settings?.[row.toggle]) : undefined;
              const description = providerDescriptions[row.id] ?? row.description;
              const needsKey = row.field && !saved && !row.keyOptional &&
                (row.toggle ? enabled : required[row.id]);
              return (
                <section className={`provider-row ${enabled === false ? "is-off" : ""}`} key={row.id}>
                  <div className="provider-row-head">
                    <div className="provider-row-copy">
                      <h3>{row.name}</h3>
                      <p className="subtle" id={`provider-description-${row.id}`}>{description}</p>
                    </div>
                    <div className="provider-row-status">
                      {row.field && (
                        <StatusPill tone={saved ? "support" : "neutral"}>
                          {saved ? "Key saved" : "No key"}
                        </StatusPill>
                      )}
                      {row.toggle && settings && (
                        <button
                          type="button"
                          role="switch"
                          aria-label={row.name}
                          aria-describedby={`provider-description-${row.id}`}
                          aria-checked={Boolean(enabled)}
                          className={`switch ${enabled ? "on" : ""}`}
                          disabled={locked || (enabledCount === 1 && enabled)}
                          onClick={() => toggle(row)}
                        >
                          <span className="switch-track" aria-hidden="true"><i /></span>
                          <span className="switch-state" aria-hidden="true">{enabled ? "On" : "Off"}</span>
                        </button>
                      )}
                    </div>
                  </div>
                  {needsKey && (
                    <p className="provider-warning" role="note">
                      {row.toggle ? "Turned on without a key. Add a key below or turn it off." : "Required by your chosen models. Add a key below."}
                    </p>
                  )}
                  {row.field && (
                    <label className="field">
                      <span>{row.name} API key</span>
                      <input
                        type="password"
                        autoComplete="off"
                        spellCheck={false}
                        disabled={busy}
                        value={keys[row.field] || ""}
                        placeholder={saved ? "Enter a key to replace the saved key" : "Paste your API key"}
                        onChange={(event) =>
                          setKeys((current) => ({ ...current, [row.field as string]: event.target.value }))
                        }
                      />
                    </label>
                  )}
                  <div className="provider-row-actions">
                    {row.field && row.vault && (
                      <>
                        <button type="button" className="btn btn-secondary btn-sm" disabled={busy || !saved} onClick={() => void check(row.id)}>
                          {row.id === "mimo" || row.id === "openai" ? "Check connection" : "Check key status"}
                        </button>
                        <button type="button" className="btn btn-ghost btn-sm" disabled={busy || !saved} onClick={() => void remove(row.vault as string, row.id)}>
                          Remove key
                        </button>
                      </>
                    )}
                    {row.limit && settings && onSettings && (
                      <label className="inline-select">
                        <span>Max requests per run</span>
                        <select
                          aria-label={`${row.name} maximum requests per run`}
                          disabled={locked || !enabled}
                          value={settings.providerRequestLimits?.[row.limit[0]] ?? ""}
                          onChange={(event) => {
                            const limits = { ...settings.providerRequestLimits };
                            const provider = (row.limit as readonly [string, number])[0];
                            if (event.target.value) limits[provider] = Number(event.target.value);
                            else delete limits[provider];
                            onSettings({ ...settings, providerRequestLimits: limits });
                          }}
                        >
                          <option value="">Auto</option>
                          {Array.from({ length: row.limit[1] }, (_, index) => index + 1)
                            .filter((limit) => row.id !== "pubmed" || limit % 2 === 0)
                            .map((limit) => <option key={limit} value={limit}>{limit}</option>)}
                        </select>
                      </label>
                    )}
                  </div>
                  {currentChecks[row.id] && (
                    <p className="connection-feedback" role="status">{currentChecks[row.id]}</p>
                  )}
                </section>
              );
            })}
          </fieldset>
        ))}
        <p className="subtle">Keys are stored in your system credential vault, never in this app&rsquo;s files or browser storage.</p>
        {message && <p className="setup-status" role="status">{message}</p>}
        <div className="form-actions">
          <button
            className="btn btn-primary"
            type="submit"
            disabled={busy || !Object.values(keys).some((value) => value.trim())}
          >
            {busy ? "Working…" : "Save keys securely"}
          </button>
        </div>
      </form>
      <details className="disclosure">
        <summary><span className="disclosure-summary">Connection troubleshooting</span></summary>
        <div className="disclosure-body">
          <p>If macOS asks for Keychain access, enter your Mac login password.</p>
          <button type="button" className="btn btn-secondary btn-sm" disabled={busy} onClick={() => void restoreStandardRoute()}>
            Reset OpenAI endpoint
          </button>
        </div>
      </details>
    </div>
  );
}
