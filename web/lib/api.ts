const API_URL = process.env.NEXT_PUBLIC_RESEARCH_API_URL ?? "http://127.0.0.1:8765";

export type ServiceDiagnostic = {
  state: "healthy" | "unhealthy" | "wrong_service" | "starting" | "exited" | "launch_failed" | "stopped";
  wigolo_ready: boolean;
  searxng_readiness: "configured" | "not_confirmed" | "unavailable";
  message: string;
  owned_process: boolean;
  pid: number | null;
  recent_output: string[];
};

export type Configuration = {
  configured: boolean;
  message: string;
  default_db_path: string;
  firecrawl_enabled: boolean;
  saved_credentials: string[];
  saved_settings: string[];
  service: ServiceDiagnostic;
};

export type ResearchProgress = {
  stance: "supporting" | "opposing";
  status: string;
  model_attempts: number;
  retrieval_attempts: number;
  usable_snapshots: number;
  candidates: number;
};

export type V2ProviderRunDiagnostics = {
  provider: string;
  query_attempts: number;
  non_empty_queries: number;
  empty_queries: number;
  timeout_queries: number;
  failed_queries: number;
  search_results: number;
  surviving_sources: number;
};

export type V2RunDiagnostics = {
  configured_providers: string[];
  provider_outcomes: V2ProviderRunDiagnostics[];
  search_attempts: number;
  search_results: number;
  acquisition_attempts: number;
  sources_acquired: number;
  sources_survived_probe: number;
  sources_queued_for_analysis: number;
  sources_analyzed: number;
  approved_evidence_records: number;
};

export type RunSnapshot = {
  run_id: string;
  db_path: string;
  raw_claim: string;
  classification: string;
  exit_code: number | null;
  stage: string;
  latest_checkpoint: string | null;
  completed_checkpoints: number;
  total_checkpoints: number;
  current_research_round: number;
  progress_percent: number;
  message: string;
  diagnostic_component: string;
  model_calls_used: number;
  retrieval_attempts_used: number;
  total_tokens: number | null;
  total_cost_usd: string | number | null;
  known_token_subtotal: number;
  known_cost_subtotal_usd: string | number;
  token_usage_complete: boolean;
  cost_usage_complete: boolean;
  model_usage_details?: {
    input_tokens: UsageTokenCount;
    output_tokens: UsageTokenCount;
    cached_input_tokens: UsageTokenCount;
    cache_write_tokens: UsageTokenCount;
    cost_basis_counts: { basis: ModelUsageCostBasis | null; physical_calls: number }[];
  } | null;
  conservative_reserved_tokens: number | null;
  conservative_reserved_cost_usd: string | number | null;
  supporting: ResearchProgress;
  opposing: ResearchProgress;
  validation_errors: string[];
  final_brief: string | null;
  rendered_brief_hash: string | null;
  provider_identity: string | null;
  model_identity: string | null;
  fingerprint: string | null;
  research_controls: {
    research_mode: "focused" | "balanced";
    sources_per_stance_per_round: 5 | 10 | 15 | 20;
    discovery_providers: string[];
  };
  v2_diagnostics: V2RunDiagnostics | null;
};

export type UsageTokenCount = {
  total: number | null;
  known_subtotal: number;
  complete: boolean;
};

export type ModelUsageCostBasis =
  | "published_cache_prices_reported_writes"
  | "published_cache_prices_assumed_all_uncached_writes"
  | "configured_price_cap";

export type HistoryItem = {
  run_id: string;
  raw_claim: string;
  status: string;
  stage: string;
  updated_at: string;
  completed_at: string | null;
};

export type ResearchTrailItem = {
  research_round: number;
  stance: "supporting" | "opposing";
  provider: "serpsearch" | "exa" | "openalex" | "arxiv" | "pubmed" | "serper";
  intent: string;
  query_text: string;
  title: string;
  url: string;
  score: number | null;
  decision: "selected" | "deferred" | "discarded";
  selection_rank: number | null;
  breakdown: {
    relevance: number;
    intent_match: number;
    directness: number;
    metadata_completeness: number;
    likely_accessibility: number;
    source_novelty: number;
    penalties: number;
  } | null;
  acquired_score: number | null;
  extraction_rank: number | null;
  acquired_breakdown: {
    readability: number;
    claim_term_coverage: number;
    document_specificity: number;
    evidence_language: number;
    penalties: number;
  } | null;
  acquisition_state: "acquired" | "attempted" | "not_attempted" | null;
};

export type V2ResultSource = {
  source_id: string;
  direction: "support" | "challenge";
  source_url: string;
  title: string | null;
  source_type: string | null;
  publication_date: string | null;
  discovery_providers: string[];
  discovery_round: number;
  recommended: boolean;
  recommendation_rank: number | null;
  queue_rank: number | null;
  status: "recommended_analyzed" | "recommended_analyzer_admitted" | "recommended_analyzer_rejected" | "recommended_analyzer_failed" | "recommended_no_ledger_evidence" | "surviving_analyzed" | "surviving_analyzer_admitted" | "surviving_analyzer_rejected" | "surviving_analyzer_failed" | "surviving_not_deeply_analyzed" | "budget_prevented_analysis";
  ledger_claim_ids: string[];
  budget_prevented_reason: string | null;
};

export type V2FinalResearchOutput = {
  run_id: string;
  exact_claim: string;
  directions: { support_enabled: boolean; challenge_enabled: boolean };
  synthesis: { sections: { section_type: "supporting" | "opposing" | "limitations"; items: { ledger_claim_id: string; approved_factual_statement: string; admission_method: "analyzer_admitted" | "reviewer_approved" }[] }[] };
  recommended_source_ids: string[];
  recommended_sources: V2ResultSource[];
  all_surviving_sources: V2ResultSource[];
  unresolved_material_gaps: { gap_id: string; direction: "support" | "challenge"; missing_evidence: string; assessed_after_round: number }[];
  claim_coverage_map?: { dimension: string; claim_component: string; coverage_state: string; evidence_summary: string }[];
  post_analysis_assessment?: V2EvidenceDisplay["post_analysis_assessment"];
  stopping: { reason: string; explanation: string; completed_rounds: number };
  release_validation: { valid: boolean; rendered_output_hash: string | null };
};

export type V2EvidenceDisplay = {
  run_id: string;
  research_status: {
    reason_code: string;
    explanation: string;
    actionable_gap_count: number;
    partial_coverage_count: number;
    unavailable_coverage_count: number;
    source: "persisted_governor" | "final_output";
  };
  study_lineage: { source_ids: string[]; basis: "matching_doi" | "matching_title"; explanation: string }[];
  shared_website_groups: { host: string; source_ids: string[]; explanation: string }[];
  post_analysis_assessment: {
    run_id: string;
    assessed_after_analysis: true;
    claim_established: false;
    admitted_source_ids: string[];
    supporting_count: number;
    challenging_count: number;
    qualifying_count: number;
    unrelated_count: number;
    unadmitted_source_count: number;
    partial_coverage_count: number;
    unavailable_coverage_count: number;
    unresolved_gap_count: number;
    claim_support_observed: boolean;
    limitations: string[];
  } | null;
  source_budget_outcomes: {
    source_id: string;
    outcome: "source_budget_blocked" | "token_cap_blocked" | "physical_call_cap_blocked";
  }[];
  items: {
    source_id: string;
    ledger_claim_id: string;
    title: string | null;
    source_url: string;
    source_type: string | null;
    source_context_notice: string | null;
    source_family: string;
    direction: "support" | "challenge";
    relationship_to_claim: "supports" | "challenges" | "qualifies" | "unrelated";
    approved_factual_statement: string;
    recommendation_status: string;
    selection_rationale: string | null;
    gap_ids: string[];
    evidence_summary: string;
    supporting_proposition: string;
    quote_passage: string;
    limitations: string[];
    validation_status: string;
  }[];
};

type StartInput = {
  model_profile: "configurable-2026-09";
  stage_models: StageModels;
  raw_claim: string;
  acknowledged_public: boolean;
  db_path: string;
  run_id: string | null;
  max_tokens: number;
  max_cost_usd: string;
  max_llm_calls: number;
  support_enabled: boolean;
  challenge_enabled: boolean;
  sources_per_stance_per_round: 5 | 10 | 15 | 20;
  use_serpsearch: boolean;
  use_exa: boolean;
  use_openalex: boolean;
  use_arxiv: boolean;
  use_pubmed: boolean;
  use_crossref: boolean;
};

export type ProviderSelection = Pick<
  StartInput,
  "use_serpsearch" | "use_exa" | "use_openalex" | "use_arxiv" | "use_pubmed"
>;

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
export type ModelChoiceId =
  | "gpt-6-luna-high"
  | "gpt-6-luna-xhigh"
  | "mimo-v2.6-pro"
  | "mimo-v2.6-flash"
  | "gpt-6-sol-high"
  | "gpt-5.6-terra-high";
export type StageModels = Record<StageModelKey, ModelChoiceId>;

export const DEFAULT_STAGE_MODELS: StageModels = {
  planner: "gpt-6-luna-xhigh",
  scout: "gpt-6-luna-high",
  gap_analysis: "gpt-6-luna-xhigh",
  search_agent: "gpt-6-luna-xhigh",
  source_selection: "gpt-6-luna-xhigh",
  extractor: "gpt-6-luna-high",
  analyst: "gpt-6-luna-xhigh",
};

export type ModelOption = {
  id: ModelChoiceId;
  label: string;
  provider: "openai" | "mimo" | string;
  input_per_million: string | number;
  output_per_million: string | number;
};

export type ModelOptions = {
  choices: ModelOption[];
  defaults: StageModels;
};

type StartResult = {
  started: boolean;
  run_id: string;
  classification: string;
  message: string;
};

type CredentialInput = {
  mimo_api_key?: string;
  luna_api_key?: string;
  luna_base_url?: string;
  luna_model?: string;
  mimo_v25_input_usd_per_million?: string;
  mimo_v25_output_usd_per_million?: string;
  luna_input_usd_per_million?: string;
  luna_output_usd_per_million?: string;
  exa_api_key?: string;
  openalex_api_key?: string;
  serpsearch_api_key?: string;
  pubmed_api_key?: string;
  firecrawl_api_key?: string;
};

function readableErrorDetail(detail: unknown): string | null {
  if (typeof detail === "string" && detail.trim()) return detail;
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
    const payload = (await response.json().catch(() => null)) as { detail?: unknown } | null;
    const detail = readableErrorDetail(payload?.detail) ?? "The local service could not complete that request.";
    throw new Error(detail);
  }
  return (await response.json()) as T;
}

async function startService(): Promise<ServiceDiagnostic> {
  const deadline = Date.now() + 30_000;
  const timedRequest = (path: string, init?: RequestInit) => request<ServiceDiagnostic>(path, {
    ...init,
    signal: AbortSignal.timeout(Math.max(1, deadline - Date.now())),
  });
  let service = await timedRequest("/api/service/start", { method: "POST" });
  while (!service.wigolo_ready && service.state === "starting") {
    if (Date.now() >= deadline) throw new Error("Research tools did not start in time. Open Settings to retry.");
    await new Promise<void>((resolve) => setTimeout(resolve, Math.min(500, deadline - Date.now())));
    if (Date.now() >= deadline) throw new Error("Research tools did not start in time. Open Settings to retry.");
    service = await timedRequest("/api/service");
  }
  return service;
}

let preferencesSaveQueue: Promise<unknown> = Promise.resolve();

function savePreferences(settings: InterfaceSettings): Promise<InterfaceSettings> {
  const body = JSON.stringify(settings);
  const operation = preferencesSaveQueue.then(() => request<InterfaceSettings>("/api/preferences", {
    method: "POST", body,
  }));
  preferencesSaveQueue = operation.catch(() => undefined);
  return operation;
}

export const researchApi = {
  profiles: () => request<ModelProfile[]>("/api/model-profiles"),
  modelOptions: () => request<ModelOptions>("/api/model-options"),
  checkConnection: (name: string, stageModels: StageModels) => request<{ state: string; message: string }>(`/api/credentials/${encodeURIComponent(name)}/check`, {
    method: "POST",
    body: JSON.stringify({ model_profile: "configurable-2026-09", stage_models: stageModels }),
  }),
  importHistory: (source: string) => request<{ db_path: string; run_count: number }>(`/api/history/import?source=${encodeURIComponent(source)}`, { method: "POST" }),
  preferences: () => request<InterfaceSettings>("/api/preferences"),
  savePreferences,
  removeCredential: (name: string) => request<{ removed: boolean }>(`/api/credentials/${encodeURIComponent(name)}/remove`, { method: "POST" }),
  configuration: (stageModels: StageModels, selection: ProviderSelection, signal?: AbortSignal) =>
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
  saveCredentials: (payload: CredentialInput, stageModels: StageModels, selection: ProviderSelection) =>
    request<{ saved: boolean; configured: boolean; message: string; saved_settings: string[] }>(`/api/credentials?${new URLSearchParams({
      use_serpsearch: String(selection.use_serpsearch),
      use_exa: String(selection.use_exa),
      use_openalex: String(selection.use_openalex),
      use_arxiv: String(selection.use_arxiv),
      use_pubmed: String(selection.use_pubmed),
    }).toString()}`, {
      method: "POST",
      body: JSON.stringify({ model_profile: "configurable-2026-09", stage_models: stageModels, ...payload }),
    }),
  start: (payload: StartInput) =>
    request<StartResult>("/api/research/start", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  snapshot: (runId: string, database: string, signal?: AbortSignal) =>
    request<RunSnapshot>(`/api/research/${runId}?db_path=${encodeURIComponent(database)}`, { signal }),
  cancel: (runId: string, database: string) =>
    request<{ cancelled: boolean; message: string }>(`/api/research/${runId}/cancel`, {
      method: "POST",
      body: JSON.stringify({ db_path: database }),
    }),
  history: (database: string) =>
    request<{ items: HistoryItem[] }>(`/api/history?db_path=${encodeURIComponent(database)}`),
  trail: (runId: string, database: string) =>
    request<{ run_id: string; items: ResearchTrailItem[] }>(`/api/research/${runId}/trail?db_path=${encodeURIComponent(database)}`),
  v2Result: (runId: string, database: string) =>
    request<V2FinalResearchOutput>(`/api/research/${runId}/v2-result?db_path=${encodeURIComponent(database)}`),
  v2Evidence: (runId: string, database: string) =>
    request<V2EvidenceDisplay>(`/api/research/${runId}/v2-evidence?db_path=${encodeURIComponent(database)}`),
  service: () => request<ServiceDiagnostic>("/api/service"),
  startService,
  stopService: () => request<ServiceDiagnostic>("/api/service/stop", { method: "POST" }),
};

export type InterfaceSettings = {
  modelProfile: "configurable-2026-09";
  stageModels: StageModels;
  dbPath: string; maxTokens: number; maxCost: string; maxCalls: number;
  supportEnabled: boolean; challengeEnabled: boolean; sourceTarget: 5 | 10 | 15 | 20;
  useSerpSearch: boolean; useExa: boolean; useOpenAlex: boolean; useArxiv: boolean;
  usePubmed: boolean; useCrossref: boolean;
};

export type ModelProfile = { id: "configurable-2026-09" | "standard-2026-09"; name: string; description: string; pricing_reviewed: string; models: { model: string; roles: string; input_per_million: string; output_per_million: string; completion_limit: number; output_contract: string }[] };
