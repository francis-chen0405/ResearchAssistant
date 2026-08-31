import type { HostedResearchRequest } from "@/lib/hosted-api";

type Props = {
  request: HostedResearchRequest;
  open: boolean;
  onClose: () => void;
  onChange: (request: HostedResearchRequest) => void;
};

const providers = [
  ["serpsearch", "SERP Search"],
  ["exa", "Exa"],
  ["openalex", "OpenAlex"],
  ["arxiv", "arXiv"],
  ["pubmed", "PubMed"],
] as const;

export function AdvancedPanel({ request, open, onClose, onChange }: Props): React.ReactElement | null {
  if (!open) return null;
  const toggleProvider = (provider: string) => {
    const next = new Set(request.discovery_providers);
    if (next.has(provider)) next.delete(provider); else next.add(provider);
    onChange({ ...request, discovery_providers: providers.map(([value]) => value).filter((value) => next.has(value)) });
  };
  return (
    <div className="panel-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}>
      <aside className="side-panel" aria-label="Advanced controls">
        <button className="close-button" type="button" onClick={onClose} aria-label="Close advanced controls">×</button>
        <p className="eyebrow">Operator controls</p>
        <h2>Set the shape of the inquiry.</h2>
        <p className="muted">These choices travel with the run. The run ID is created by the server when you start.</p>
        <div className="control-stack">
          <label>Token ceiling<input type="number" min={1} max={500000} value={request.max_tokens} onChange={(event) => onChange({ ...request, max_tokens: Number(event.target.value) })} /></label>
          <label>Cost ceiling<input type="number" min={0.01} max={1} step={0.01} value={request.max_cost_usd} onChange={(event) => onChange({ ...request, max_cost_usd: event.target.value })} /></label>
          <label>Model calls<input type="number" min={1} max={160} value={request.max_llm_calls} onChange={(event) => onChange({ ...request, max_llm_calls: Number(event.target.value) })} /></label>
          <label>Sources per direction<select value={request.sources_per_stance_per_round} onChange={(event) => onChange({ ...request, sources_per_stance_per_round: Number(event.target.value) as HostedResearchRequest["sources_per_stance_per_round"] })}><option value={5}>5</option><option value={10}>10</option><option value={15}>15</option><option value={20}>20</option></select></label>
        </div>
        <div className="toggle-list">
          <label><input type="checkbox" checked={request.support_enabled} onChange={(event) => onChange({ ...request, support_enabled: event.target.checked })} /> Support evidence</label>
          <label><input type="checkbox" checked={request.challenge_enabled} onChange={(event) => onChange({ ...request, challenge_enabled: event.target.checked })} /> Challenge evidence</label>
          <label><input type="checkbox" checked={request.crossref_enabled} onChange={(event) => onChange({ ...request, crossref_enabled: event.target.checked })} /> Crossref enrichment</label>
        </div>
        <p className="eyebrow section-label">Discovery lanes</p>
        <div className="provider-grid">{providers.map(([value, label]) => <label key={value}><input type="checkbox" checked={request.discovery_providers.includes(value)} onChange={() => toggleProvider(value)} /> {label}</label>)}</div>
      </aside>
    </div>
  );
}
