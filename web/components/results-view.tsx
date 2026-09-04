import type { HostedArtifact, HostedRun } from "@/lib/hosted-api";

type Props = { run: HostedRun; artifacts: HostedArtifact[]; onBack: () => void };

function artifactPayload(artifacts: HostedArtifact[]): Record<string, unknown> | null {
  const artifact = artifacts.find((item) => /final|release|synthesis/i.test(item.artifact_type));
  if (!artifact) return null;
  try {
    const payload = JSON.parse(artifact.payload_json) as unknown;
    return payload && typeof payload === "object" && !Array.isArray(payload) ? payload as Record<string, unknown> : null;
  } catch { return null; }
}

function stringValue(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value : null;
}

export function ResultsView({ run, artifacts, onBack }: Props): React.ReactElement {
  const payload = artifactPayload(artifacts);
  const brief = ["final_brief", "rendered_brief", "brief"].map((key) => stringValue(payload?.[key])).find(Boolean) ?? stringValue(payload?.synthesis);
  const sources = Array.isArray(payload?.recommended_sources) ? payload.recommended_sources.filter((item): item is Record<string, unknown> => Boolean(item && typeof item === "object" && stringValue((item as Record<string, unknown>).source_url))) : [];
  const gaps = Array.isArray(payload?.unresolved_material_gaps) ? payload.unresolved_material_gaps.filter((item): item is Record<string, unknown> => Boolean(item && typeof item === "object")) : [];
  const release = payload?.release_validation && typeof payload.release_validation === "object" ? payload.release_validation as Record<string, unknown> : null;
  const downloadText = brief ?? `Research record\n\n${run.raw_claim}\n\n${run.message}`;
  return <section className="results-layout"><div className="results-main"><button type="button" className="back-link" onClick={onBack}>← New inquiry</button><p className="eyebrow">{run.status === "released" ? "Released brief" : "Research record"}</p><h2>{run.raw_claim}</h2>{brief ? <div className="brief-copy"><p>{brief}</p></div> : <div className="empty-state"><h3>No release artifact yet.</h3><p className="muted">This run is preserved with its status and evidence trail.</p></div>}{sources.length ? <section className="result-section"><p className="eyebrow">Recommended sources</p>{sources.map((source, index) => <a className="source-link" href={stringValue(source.source_url) ?? "#"} target="_blank" rel="noreferrer" key={`${stringValue(source.source_id) ?? index}`}>{stringValue(source.title) ?? stringValue(source.source_url)} <span>↗</span></a>)}</section> : null}{gaps.length ? <section className="result-section"><p className="eyebrow">Unresolved gaps</p>{gaps.map((gap, index) => <p className="gap-line" key={`${stringValue(gap.gap_id) ?? index}`}>{stringValue(gap.missing_evidence) ?? "Evidence gap retained in the record."}</p>)}</section> : null}</div><aside className="results-aside"><div className="status-stamp"><span>{run.status}</span><small>run state</small></div><dl><div><dt>Checkpoints</dt><dd>{run.completed_checkpoints}/{run.total_checkpoints}</dd></div><div><dt>Artifacts</dt><dd>{artifacts.length}</dd></div><div><dt>Release hash</dt><dd>{stringValue(release?.rendered_output_hash)?.slice(0, 12) ?? "Pending"}</dd></div></dl><p className="muted small">Artifacts are immutable once accepted into the hosted record.</p><a className="download-link" download="researchassistant-brief.txt" href={`data:text/plain;charset=utf-8,${encodeURIComponent(downloadText)}`}>Download brief <b>↓</b></a><details className="artifact-list"><summary>Inspect artifact trail</summary>{artifacts.map((artifact) => <p key={artifact.artifact_id}><strong>{artifact.artifact_type}</strong><code>{artifact.fingerprint.slice(0, 16)}…</code></p>)}</details></aside></section>;
}
