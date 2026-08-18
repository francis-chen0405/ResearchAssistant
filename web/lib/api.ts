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
  };
};

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
  provider: "exa" | "openalex";
  intent: string;
  query_text: string;
  title: string;
  url: string;
  score: number;
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
  };
  acquired_score: number | null;
  extraction_rank: number | null;
  acquired_breakdown: {
    readability: number;
    claim_term_coverage: number;
    document_specificity: number;
    evidence_language: number;
    penalties: number;
  } | null;
};

type StartInput = {
  raw_claim: string;
  acknowledged_public: boolean;
  db_path: string;
  run_id: string | null;
  max_tokens: number;
  max_cost_usd: string;
  max_llm_calls: number;
  include_counterevidence: boolean;
  sources_per_stance_per_round: 5 | 10 | 15 | 20;
};

type StartResult = {
  started: boolean;
  run_id: string;
  classification: string;
  message: string;
};

type CredentialInput = {
  mimo_api_key: string;
  exa_api_key: string;
  openalex_api_key: string;
  firecrawl_api_key?: string;
};

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
    cache: "no-store",
  });
  if (!response.ok) {
    const payload = (await response.json().catch(() => null)) as { detail?: unknown } | null;
    const detail = typeof payload?.detail === "string" ? payload.detail : "The local service could not complete that request.";
    throw new Error(detail);
  }
  return (await response.json()) as T;
}

export const researchApi = {
  configuration: () => request<Configuration>("/api/configuration"),
  saveCredentials: (payload: CredentialInput) =>
    request<{ saved: boolean; configured: boolean; message: string }>("/api/credentials", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  start: (payload: StartInput) =>
    request<StartResult>("/api/research/start", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  snapshot: (runId: string, database: string) =>
    request<RunSnapshot>(`/api/research/${runId}?db_path=${encodeURIComponent(database)}`),
  cancel: (runId: string, database: string) =>
    request<{ cancelled: boolean; message: string }>(`/api/research/${runId}/cancel`, {
      method: "POST",
      body: JSON.stringify({ db_path: database }),
    }),
  history: (database: string) =>
    request<{ items: HistoryItem[] }>(`/api/history?db_path=${encodeURIComponent(database)}`),
  trail: (runId: string, database: string) =>
    request<{ run_id: string; items: ResearchTrailItem[] }>(`/api/research/${runId}/trail?db_path=${encodeURIComponent(database)}`),
  service: () => request<ServiceDiagnostic>("/api/service"),
  startService: () => request<ServiceDiagnostic>("/api/service/start", { method: "POST" }),
  stopService: () => request<ServiceDiagnostic>("/api/service/stop", { method: "POST" }),
};
