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
    discovery_providers: string[];
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
  provider: "serpsearch" | "exa" | "openalex" | "arxiv" | "pubmed" | "serper";
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
  status: "recommended_analyzed" | "recommended_no_ledger_evidence" | "surviving_analyzed" | "surviving_not_deeply_analyzed" | "budget_prevented_analysis";
  ledger_claim_ids: string[];
  budget_prevented_reason: string | null;
};

export type V2FinalResearchOutput = {
  run_id: string;
  exact_claim: string;
  directions: { support_enabled: boolean; challenge_enabled: boolean };
  synthesis: { sections: { section_type: "supporting" | "opposing" | "limitations"; items: { approved_factual_statement: string }[] }[] };
  recommended_source_ids: string[];
  recommended_sources: V2ResultSource[];
  all_surviving_sources: V2ResultSource[];
  unresolved_material_gaps: { gap_id: string; direction: "support" | "challenge"; missing_evidence: string; assessed_after_round: number }[];
  stopping: { reason: string; explanation: string; completed_rounds: number };
  release_validation: { valid: boolean; rendered_output_hash: string | null };
};

export type V2EvidenceDisplay = {
  run_id: string;
  items: {
    source_id: string;
    title: string | null;
    source_url: string;
    source_family: string;
    direction: "support" | "challenge";
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
  v2Result: (runId: string, database: string) =>
    request<V2FinalResearchOutput>(`/api/research/${runId}/v2-result?db_path=${encodeURIComponent(database)}`),
  v2Evidence: (runId: string, database: string) =>
    request<V2EvidenceDisplay>(`/api/research/${runId}/v2-evidence?db_path=${encodeURIComponent(database)}`),
  service: () => request<ServiceDiagnostic>("/api/service"),
  startService: () => request<ServiceDiagnostic>("/api/service/start", { method: "POST" }),
  stopService: () => request<ServiceDiagnostic>("/api/service/stop", { method: "POST" }),
};
