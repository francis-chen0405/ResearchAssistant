import type { HostedRun } from "@/lib/hosted-api";

type Props = { run: HostedRun; onCancel: () => void };
const stages = ["planning", "discovery", "acquisition", "gap_analysis", "adaptive_search", "deep_analysis", "evidence_admission", "synthesis", "validation"];

export function ProgressView({ run, onCancel }: Props): React.ReactElement {
  const current = stages.indexOf(run.stage);
  return <section className="workspace-card progress-card" aria-live="polite">
    <div className="progress-top"><div><p className="eyebrow">Live research · attempt {run.attempt || 1}</p><h2>{run.raw_claim}</h2><p className="muted">{run.message}</p></div><div className="progress-ring" style={{ "--progress": `${run.progress_percent}%` } as React.CSSProperties}><strong>{run.progress_percent}</strong><span>%</span></div></div>
    <div className="stage-rail" aria-label="Research progress">{stages.map((stage, index) => <div className={index < current ? "done" : index === current ? "current" : ""} key={stage}><i /><span>{String(index + 1).padStart(2, "0")}</span><b>{stage.replaceAll("_", " ")}</b></div>)}</div>
    <div className="run-meta"><span>Checkpoint <b>{run.latest_checkpoint ?? "Starting"}</b></span><span>Run <b>{run.run_id.slice(0, 8)}…</b></span>{run.status === "queued" || run.status === "running" ? <button type="button" className="quiet-button" onClick={onCancel}>Cancel</button> : null}</div>
  </section>;
}
