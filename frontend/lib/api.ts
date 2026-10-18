import type { ApiSchemas, ApiResponses } from "./generated/api-contracts";

// FastAPI emits defaulted fields in these current response envelopes. Nested
// historical optional fields stay optional in the generated schema.
export type ServiceDiagnostic = ApiSchemas["ServiceDiagnostic"];
export type Configuration = Required<
  ApiResponses["POST /api/configuration/check"]
>;
export type ResearchProgress = ApiSchemas["ResearchProgress"];
export type V2ProviderRunDiagnostics = ApiSchemas["V2ProviderRunDiagnostics"];
export type V2RunDiagnostics = ApiSchemas["V2RunDiagnostics"] &
  Required<
    Pick<
      ApiSchemas["V2RunDiagnostics"],
      | "configured_providers"
      | "provider_outcomes"
      | "search_attempts"
      | "search_results"
      | "acquisition_attempts"
      | "sources_acquired"
      | "sources_survived_probe"
      | "sources_queued_for_analysis"
      | "sources_analyzed"
      | "approved_evidence_records"
    >
  >;
export type RunSnapshot = Omit<
  Required<ApiResponses["GET /api/research/{run_id}"]>,
  "research_controls" | "v2_diagnostics"
> & {
  research_controls: ApiSchemas["ResearchControls"] &
    Required<
      Pick<
        ApiSchemas["ResearchControls"],
        "research_mode" | "sources_per_stance_per_round" | "discovery_providers"
      >
    >;
  v2_diagnostics: V2RunDiagnostics | null;
};
export type UsageTokenCount = ApiSchemas["LiveTokenCount"];
export type ModelUsageCostBasis = ApiSchemas["ModelUsageCostBasis"];
export type HistoryItem = ApiSchemas["LiveHistoryItem"];
export type RecordCompatibilityResult = ApiSchemas["RecordCompatibilityResult"];
export type SourcePreview = ApiSchemas["V2PreviewResult"];
export type ResearchTrail = ApiResponses["GET /api/research/{run_id}/trail"];
export type ResearchTrailItem = ApiSchemas["ResearchTrailItem"];
export type SourceLeadsResponse = Required<
  ApiResponses["GET /api/research/{run_id}/source-leads"]
>;
export type SourceLead = SourceLeadsResponse["items"][number];
export type V2ResultSource = ApiSchemas["V2ResultSource"];
export type V2FinalResearchOutput =
  ApiResponses["GET /api/research/{run_id}/v2-result"];
export type V2EvidenceDisplay = Required<
  ApiResponses["GET /api/research/{run_id}/v2-evidence"]
>;
export type StartInput = ApiSchemas["ResearchStartInput"];
export type ProviderSelection = Required<
  Pick<
    StartInput,
    "use_serpsearch" | "use_exa" | "use_openalex" | "use_arxiv" | "use_pubmed"
  >
>;

const API_URL =
  process.env.NEXT_PUBLIC_RESEARCH_API_URL ?? "http://127.0.0.1:8765";

export const STAGE_MODEL_KEYS = [
  "planner",
  "scout",
  "gap_analysis",
  "search_agent",
  "source_selection",
  "extractor",
  "analyst",
] as const;

export type StageModelKey = (typeof STAGE_MODEL_KEYS)[number];
export type ModelChoiceId = ApiSchemas["ModelChoice"];
export type StageModels = Required<ApiSchemas["StageModelSelections"]>;

export const DEFAULT_STAGE_MODELS: StageModels = {
  planner: "gpt-6-luna-xhigh",
  scout: "gpt-6-luna-high",
  gap_analysis: "gpt-6-luna-xhigh",
  search_agent: "gpt-6-luna-xhigh",
  source_selection: "gpt-6-luna-xhigh",
  extractor: "gpt-6-luna-high",
  analyst: "gpt-6-luna-xhigh",
};

export type ModelOption = ApiSchemas["ModelOptionDisplay"];
export type ModelOptions = Omit<
  ApiResponses["GET /api/model-options"],
  "defaults"
> & { defaults: StageModels };
type StartResult = ApiResponses["POST /api/research/start"];
type CredentialInput = Omit<
  ApiSchemas["CredentialSetupRequest"],
  "model_profile" | "stage_models"
>;

function readableErrorDetail(detail: unknown): string | null {
  if (typeof detail === "string" && detail.trim()) return detail;
  if (detail && typeof detail === "object" && !Array.isArray(detail)) {
    const message = (detail as { message?: unknown }).message;
    return typeof message === "string" && message.trim() ? message : null;
  }
  if (!Array.isArray(detail)) return null;
  const messages = detail.flatMap((item): string[] => {
    if (!item || typeof item !== "object") return [];
    const message = (item as { msg?: unknown }).msg;
    return typeof message === "string" && message.trim() ? [message] : [];
  });
  return messages.length ? messages.join(" ") : null;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
    cache: "no-store",
  });
  if (!response.ok) {
    const payload = (await response.json().catch(() => null)) as {
      detail?: unknown;
    } | null;
    const detail =
      readableErrorDetail(payload?.detail) ??
      "The local service could not complete that request.";
    throw new Error(detail);
  }
  return (await response.json()) as T;
}

async function startService(): Promise<ServiceDiagnostic> {
  const deadline = Date.now() + 30_000;
  const timedRequest = (path: string, init?: RequestInit) =>
    request<ServiceDiagnostic>(path, {
      ...init,
      signal: AbortSignal.timeout(Math.max(1, deadline - Date.now())),
    });
  let service = await timedRequest("/api/service/start", { method: "POST" });
  while (!service.wigolo_ready && service.state === "starting") {
    if (Date.now() >= deadline)
      throw new Error(
        "Research tools did not start in time. Open Settings to retry.",
      );
    await new Promise<void>((resolve) =>
      setTimeout(resolve, Math.min(500, deadline - Date.now())),
    );
    if (Date.now() >= deadline)
      throw new Error(
        "Research tools did not start in time. Open Settings to retry.",
      );
    service = await timedRequest("/api/service");
  }
  return service;
}

let preferencesSaveQueue: Promise<unknown> = Promise.resolve();

function savePreferences(
  settings: InterfaceSettings,
): Promise<InterfaceSettings> {
  const body = JSON.stringify(settings);
  const operation = preferencesSaveQueue.then(() =>
    request<InterfaceSettings>("/api/preferences", {
      method: "POST",
      body,
    }),
  );
  preferencesSaveQueue = operation.catch(() => undefined);
  return operation;
}

export const researchApi = {
  profiles: () => request<ModelProfile[]>("/api/model-profiles"),
  modelOptions: () => request<ModelOptions>("/api/model-options"),
  checkConnection: (name: string, stageModels: StageModels) =>
    request<ApiResponses["POST /api/credentials/{name}/check"]>(
      `/api/credentials/${encodeURIComponent(name)}/check`,
      {
        method: "POST",
        body: JSON.stringify({
          model_profile: "configurable-2026-09",
          stage_models: stageModels,
        }),
      },
    ),
  importHistory: (source: string, signal?: AbortSignal) =>
    request<ApiResponses["POST /api/history/import"]>(
      `/api/history/import?source=${encodeURIComponent(source)}`,
      { method: "POST", signal },
    ),
  preferences: (signal?: AbortSignal) =>
    request<InterfaceSettings>("/api/preferences", { signal }),
  savePreferences,
  removeCredential: (name: string) =>
    request<ApiResponses["POST /api/credentials/{name}/remove"]>(
      `/api/credentials/${encodeURIComponent(name)}/remove`,
      { method: "POST" },
    ),
  configuration: (
    stageModels: StageModels,
    selection: ProviderSelection,
    signal?: AbortSignal,
  ) =>
    request<Configuration>("/api/configuration/check", {
      method: "POST",
      signal,
      body: JSON.stringify({
        model_profile: "configurable-2026-09",
        stage_models: stageModels,
        use_serpsearch: selection.use_serpsearch,
        use_exa: selection.use_exa,
        use_openalex: selection.use_openalex,
        use_arxiv: selection.use_arxiv,
        use_pubmed: selection.use_pubmed,
      }),
    }),
  saveCredentials: (
    payload: CredentialInput,
    stageModels: StageModels,
    selection: ProviderSelection,
  ) =>
    request<ApiResponses["POST /api/credentials"]>(
      `/api/credentials?${new URLSearchParams({
        use_serpsearch: String(selection.use_serpsearch),
        use_exa: String(selection.use_exa),
        use_openalex: String(selection.use_openalex),
        use_arxiv: String(selection.use_arxiv),
        use_pubmed: String(selection.use_pubmed),
      }).toString()}`,
      {
        method: "POST",
        body: JSON.stringify({
          model_profile: "configurable-2026-09",
          stage_models: stageModels,
          ...payload,
        }),
      },
    ),
  start: (payload: StartInput) =>
    request<StartResult>("/api/research/start", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  snapshot: (runId: string, database: string, signal?: AbortSignal) =>
    request<RunSnapshot>(
      `/api/research/${runId}?db_path=${encodeURIComponent(database)}`,
      { signal },
    ),
  cancel: (runId: string, database: string) =>
    request<ApiResponses["POST /api/research/{run_id}/cancel"]>(
      `/api/research/${runId}/cancel`,
      {
        method: "POST",
        body: JSON.stringify({ db_path: database }),
      },
    ),
  history: (database: string) =>
    request<ApiResponses["GET /api/history"]>(
      `/api/history?db_path=${encodeURIComponent(database)}`,
    ),
  trail: (runId: string, database: string, signal?: AbortSignal) =>
    request<ApiResponses["GET /api/research/{run_id}/trail"]>(
      `/api/research/${runId}/trail?db_path=${encodeURIComponent(database)}`,
      { signal },
    ),
  sourceLeads: (
    runId: string,
    database: string,
    offset = 0,
    limit = 50,
    signal?: AbortSignal,
  ) =>
    request<SourceLeadsResponse>(
      `/api/research/${runId}/source-leads?${new URLSearchParams({
        db_path: database,
        offset: String(offset),
        limit: String(limit),
      }).toString()}`,
      { signal },
    ),
  v2Result: (runId: string, database: string, signal?: AbortSignal) =>
    request<V2FinalResearchOutput>(
      `/api/research/${runId}/v2-result?db_path=${encodeURIComponent(database)}`,
      { signal },
    ),
  v2Evidence: (runId: string, database: string, signal?: AbortSignal) =>
    request<V2EvidenceDisplay>(
      `/api/research/${runId}/v2-evidence?db_path=${encodeURIComponent(database)}`,
      { signal },
    ),
  service: () => request<ServiceDiagnostic>("/api/service"),
  startService,
  stopService: () =>
    request<ServiceDiagnostic>("/api/service/stop", { method: "POST" }),
};

export type InterfaceSettings = Omit<
  Required<ApiSchemas["InterfaceSettings"]>,
  "modelProfile" | "stageModels"
> & {
  modelProfile: "configurable-2026-09";
  stageModels: StageModels;
};
export type ModelProfile = Omit<ApiSchemas["ModelProfile"], "models"> & {
  models: Required<ApiSchemas["SupportedModel"]>[];
};
