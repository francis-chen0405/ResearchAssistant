"use client";
import { FormEvent, useEffect, useRef, useState } from "react";
import {
  Configuration,
  ProviderSelection,
  StageModels,
  researchApi,
} from "@/lib/api";
import { Dialog } from "./dialog";
import { StatusPill } from "./workspace";

const providers = [
  {
    id: "mimo",
    field: "mimo_api_key",
    vault: "MIMO_API_KEY",
    name: "Xiaomi MiMo",
    description: "Finds, selects and extracts research. Required.",
  },
  {
    id: "openai",
    field: "luna_api_key",
    vault: "LUNA_API_KEY",
    name: "OpenAI",
    description: "Provides the selected GPT models for your research roles.",
  },
  {
    id: "serpsearch",
    field: "serpsearch_api_key",
    vault: "SERPSEARCH_API_KEY",
    name: "SERP Search",
    description: "Web search. Required when selected.",
  },
  {
    id: "brave",
    field: "brave_api_key",
    vault: "BRAVE_API_KEY",
    name: "Brave Search",
    description: "Independent web search.",
  },
  {
    id: "serper",
    field: "serper_api_key",
    vault: "SERPER_API_KEY",
    name: "Serper",
    description: "Google web results.",
  },
  {
    id: "exa",
    field: "exa_api_key",
    vault: "EXA_API_KEY",
    name: "Exa",
    description: "Search by meaning. Required when selected.",
  },
  {
    id: "openalex",
    field: "openalex_api_key",
    vault: "OPENALEX_API_KEY",
    name: "OpenAlex",
    description: "Scholarly literature. Required when selected.",
  },
  {
    id: "pubmed",
    field: "pubmed_api_key",
    vault: "PUBMED_API_KEY",
    name: "PubMed",
    description: "Optional key for a higher request allowance.",
  },
  {
    id: "firecrawl",
    field: "firecrawl_api_key",
    vault: "FIRECRAWL_API_KEY",
    name: "Firecrawl",
    description: "Optional source-reading fallback.",
  },
] as const;

type ConnectionChecks = {
  stageModelsKey: string;
  messages: Record<string, string>;
};

export function ProviderSetup({
  configuration,
  selectedProviders,
  stageModels,
  onClose,
  onSaved,
}: {
  configuration: Configuration | null;
  selectedProviders: ProviderSelection;
  stageModels: StageModels;
  onClose: () => void;
  onSaved: (message: string) => Promise<void>;
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
  return (
    <Dialog title="Provider connections" onClose={onClose} wide>
      <form className="connections-form" onSubmit={submit}>
        <div className="connection-grid">
          {providers.map((provider) => {
            const saved = configuration?.saved_credentials.includes(
              provider.id,
            );
            const description =
              providerDescriptions[provider.id] ?? provider.description;
            return (
              <section className="connection-card" key={provider.id}>
                <div className="connection-heading">
                  <h3>{provider.name}</h3>
                  <StatusPill tone={saved ? "support" : "neutral"}>
                    {saved ? "Key saved" : "Not connected"}
                  </StatusPill>
                </div>
                <p>{description}</p>
                <label>
                  {provider.name} API key
                  <input
                    type="password"
                    autoComplete="off"
                    spellCheck={false}
                    disabled={busy}
                    value={keys[provider.field] || ""}
                    placeholder={
                      saved
                        ? "Enter a key to replace the saved key"
                        : "Paste your API key"
                    }
                    onChange={(event) =>
                      setKeys((current) => ({
                        ...current,
                        [provider.field]: event.target.value,
                      }))
                    }
                  />
                </label>
                <div className="connection-actions">
                  <button
                    type="button"
                    disabled={busy || !saved}
                    onClick={() => void check(provider.id)}
                  >
                    {provider.id === "mimo" || provider.id === "openai"
                      ? "Check connection"
                      : "Check key status"}
                  </button>
                  <button
                    type="button"
                    disabled={busy || !saved}
                    onClick={() => void remove(provider.vault, provider.id)}
                  >
                    Remove key
                  </button>
                </div>
                {currentChecks[provider.id] && (
                  <p className="connection-feedback" role="status">
                    {currentChecks[provider.id]}
                  </p>
                )}
              </section>
            );
          })}
        </div>
        <p className="security-note">
          Keys are stored in your system credential vault.
        </p>
        {message && (
          <p className="setup-status" role="status">
            {message}
          </p>
        )}
        <button
          className="primary-action"
          type="submit"
          disabled={busy || !Object.values(keys).some((value) => value.trim())}
        >
          {busy ? "Working…" : "Save keys securely"}{" "}
          <span aria-hidden="true">↗</span>
        </button>
      </form>
      <details className="advanced-details">
        <summary>Connection troubleshooting</summary>
        <p>If macOS prompts for Keychain access, enter your Mac login password.</p>
        <button
          type="button"
          disabled={busy}
          onClick={() => void restoreStandardRoute()}
        >
          Reset OpenAI endpoint
        </button>
      </details>
    </Dialog>
  );
}
