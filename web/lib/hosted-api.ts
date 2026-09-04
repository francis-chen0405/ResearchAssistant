export type AuthenticatedUser = { subject: string; email: string | null; role: string };

export type HostedResearchRequest = {
  raw_claim: string;
  acknowledged_public: boolean;
  max_tokens: number;
  max_cost_usd: string;
  max_llm_calls: number;
  support_enabled: boolean;
  challenge_enabled: boolean;
  sources_per_stance_per_round: 5 | 10 | 15 | 20;
  discovery_providers: string[];
  crossref_enabled: boolean;
};

export type HostedRun = {
  run_id: string;
  owner_id: string;
  raw_claim: string;
  request: HostedResearchRequest;
  status: "queued" | "running" | "released" | "blocked" | "failed" | "cancelled";
  stage: string;
  progress_percent: number;
  message: string;
  latest_checkpoint: string | null;
  completed_checkpoints: number;
  total_checkpoints: number;
  attempt: number;
  max_attempts: number;
  lease_expires_at: string | null;
  created_at: string;
  updated_at: string;
  completed_at: string | null;
};

export type HostedEvent = {
  event_id: string;
  run_id: string;
  owner_id: string;
  event_type: string;
  stage: string;
  message: string;
  checkpoint: string | null;
  created_at: string;
};

export type HostedArtifact = {
  artifact_id: string;
  run_id: string;
  owner_id: string;
  artifact_type: string;
  fingerprint: string;
  payload_json: string;
  created_at: string;
};

export type HostedRunDetail = { run: HostedRun; events: HostedEvent[]; artifacts: HostedArtifact[] };
export type HostedHistoryItem = {
  run_id: string;
  raw_claim: string;
  status: HostedRun["status"];
  stage: string;
  updated_at: string;
  completed_at: string | null;
};
export type HostedSettings = {
  display_name: string | null;
  default_max_tokens: number;
  default_max_cost_usd: string | number;
  default_max_llm_calls: number;
};
export type CredentialMetadata = { name: string; configured: boolean; updated_at: string | null };
export type CredentialUpdate = Partial<Record<string, string>>;
export type MigrationResult = {
  source_fingerprint: string;
  imported: number;
  already_imported: number;
  collisions: string[];
  history_only: number;
};

function readableError(detail: unknown): string | null {
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
  const response = await fetch(`/api/hosted${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
    cache: "no-store",
  });
  if (!response.ok) {
    const payload = (await response.json().catch(() => null)) as { detail?: unknown } | null;
    throw new Error(readableError(payload?.detail) ?? "The hosted service could not complete that request.");
  }
  return (await response.json()) as T;
}

export const hostedApi = {
  me: () => request<{ user: AuthenticatedUser }>("/v1/auth/me"),
  start: (payload: HostedResearchRequest) => request<{ run_id: string; status: string; message: string }>("/v1/research", { method: "POST", body: JSON.stringify(payload) }),
  detail: (runId: string) => request<HostedRunDetail>(`/v1/research/${encodeURIComponent(runId)}`),
  cancel: (runId: string) => request<HostedRun>(`/v1/research/${encodeURIComponent(runId)}/cancel`, { method: "POST" }),
  history: () => request<{ items: HostedHistoryItem[] }>("/v1/history"),
  settings: () => request<HostedSettings>("/v1/settings"),
  saveSettings: (settings: HostedSettings) => request<HostedSettings>("/v1/settings", { method: "PUT", body: JSON.stringify(settings) }),
  credentials: () => request<{ credentials: CredentialMetadata[] }>("/v1/providers/credentials"),
  saveCredentials: (credentials: CredentialUpdate) => request<{ credentials: CredentialMetadata[] }>("/v1/providers/credentials", { method: "PUT", body: JSON.stringify(credentials) }),
  clearCredential: (name: string) => request<{ credentials: CredentialMetadata[] }>(`/v1/providers/credentials/${encodeURIComponent(name)}`, { method: "DELETE" }),
  importHistory: (bundle: unknown) => request<MigrationResult>("/v1/migrations/local-history", { method: "POST", body: JSON.stringify(bundle) }),
};

export async function requestMagicLink(email: string): Promise<void> {
  const response = await fetch("/api/auth/magic-link", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email }),
  });
  if (!response.ok) {
    const payload = (await response.json().catch(() => null)) as { detail?: unknown } | null;
    throw new Error(readableError(payload?.detail) ?? "The sign-in link could not be sent.");
  }
}

export async function signOut(): Promise<void> {
  await fetch("/api/auth/sign-out", { method: "POST" });
}
