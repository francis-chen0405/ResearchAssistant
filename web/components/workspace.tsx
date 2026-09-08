"use client";

import { ReactNode, useState } from "react";
import { previewEvidence, previewQuestion, previewStates } from "@/lib/preview";

export function StatusPill({ children, tone = "neutral" }: { children: ReactNode; tone?: "neutral" | "support" | "challenge" | "active" }) {
  return <span className={`status-pill ${tone}`}><i aria-hidden="true" />{children}</span>;
}

export function WorkspaceFrame({ title, status, example = false, children }: { title: string; status: ReactNode; example?: boolean; children: ReactNode }) {
  return <section className={`workspace-frame ${example ? "example-workspace" : "live-workspace"}`} aria-label={example ? "Interactive research example" : "Research workspace"}>
    <div className="workspace-chrome"><span className="window-dots" aria-hidden="true"><i /><i /><i /></span><span>{title}</span>{status}</div>
    <div className="workspace-interior">{children}</div>
  </section>;
}

export function ProgressPath({ labels, current }: { labels: string[]; current: number }) {
  return <ol className="progress-path" aria-label="Research stages">{labels.map((label, index) => <li key={label} className={index < current ? "done" : index === current ? "current" : ""} aria-current={index === current ? "step" : undefined}><span>{index < current ? "✓" : String(index + 1).padStart(2, "0")}</span><b>{label}</b></li>)}</ol>;
}

export function EvidenceTile({ title, direction, quote, context, sourceLabel }: { title: string; direction: "support" | "challenge"; quote: string; context: string; sourceLabel: string }) {
  return <article className={`evidence-tile ${direction}`}><div><StatusPill tone={direction}>{direction === "support" ? "Supporting" : "Challenging"}</StatusPill><small>{sourceLabel}</small></div><h3>{title}</h3><blockquote>“{quote}”</blockquote><details><summary>Source context <span aria-hidden="true">↗</span></summary><p>{context}</p></details></article>;
}

export function ProductPreview() {
  const [step, setStep] = useState(0);
  const [direction, setDirection] = useState<"support" | "challenge">("support");
  const isError = step === 4;
  return <div className="preview-wrap">
    <WorkspaceFrame title="A question. A traceable answer." example status={<StatusPill>Interactive example</StatusPill>}>
      <div className="workspace-topline"><span className="workspace-kicker">RESEARCH NOTEBOOK / EXAMPLE</span><StatusPill tone={isError ? "challenge" : step === 3 ? "support" : "active"}>{previewStates[step]}</StatusPill></div>
      <div className="preview-columns"><div className="preview-primary"><p className="workspace-kicker">THE QUESTION</p><h2>{previewQuestion}</h2><p className="workspace-description">Follow the evidence. Keep the context.</p>
        <div className="preview-direction" role="group" aria-label="Example research direction">{(["support", "challenge"] as const).map(value => <button type="button" key={value} aria-pressed={direction === value} onClick={() => setDirection(value)}>{value === "support" ? "+ Support" : "− Challenge"}</button>)}</div>
        <div className="preview-config"><span>Model profile<strong>Standard research</strong></span><span>Model budget<strong>$0.20 limit</strong></span></div>
        <ProgressPath labels={["Preparing", "Finding evidence", "Checking sources", "Synthesis"]} current={isError ? 1 : step} />
        <div className={`preview-conclusion ${step === 3 ? "complete" : ""}`} aria-live="polite"><span className="workspace-kicker">{isError ? "RECOVERABLE INTERRUPTION" : step === 3 ? "THE TAKEAWAY" : "YOUR EVIDENCE TRAIL"}</span><p>{isError ? "The example connection was interrupted. Collected work stays available. Retry when you’re ready." : step === 3 ? "Greener streets may help, with important local differences. A useful answer keeps both the finding and its limits in view." : step === 0 ? "Start the example to see a question become a source-backed research brief." : "Sources are collected and checked before a finding can enter the final brief."}</p>{step === 3 && <small>2 illustrative sources · provenance available</small>}</div>
      </div><div className="preview-evidence"><div className="evidence-stack-heading"><span>Evidence collected</span><b>{step === 0 ? "00" : step === 1 || isError ? "01" : "02"}</b></div>{step === 0 ? <div className="evidence-placeholder"><span aria-hidden="true">↗</span><h3>Every finding starts<br />with a source.</h3><p>Exact passages, visible context,<br />and room for uncertainty.</p><div className="placeholder-lines" aria-hidden="true"><i /><i /><i /></div></div> : previewEvidence.slice(0, step === 1 || isError ? 1 : 2).sort((a) => a.direction === direction ? -1 : 1).map(item => <EvidenceTile key={item.title} {...item} sourceLabel={item.kind} />)}<div className="preview-budget"><span>Example model usage</span><strong>{step === 0 ? "$0.00" : step === 1 || isError ? "$0.03" : "$0.08"}<small> / $0.20</small></strong><progress max={20} value={step === 0 ? 0 : step === 1 || isError ? 3 : 8} /><small>Illustrative amounts · no provider calls</small></div></div></div>
      <div className="preview-controls"><span>Explore at your own pace. No live research.</span><div><button type="button" onClick={() => setStep(step === 4 ? 1 : 4)}>{isError ? "Retry example" : "Show interruption"}</button><button type="button" className="preview-next" onClick={() => setStep(step >= 3 ? 0 : step + 1)}>{step === 0 ? "Play example" : step >= 3 ? "Replay" : "Next stage"} <span aria-hidden="true">→</span></button></div></div>
    </WorkspaceFrame><p className="preview-caption">An illustrative walkthrough. Your real research uses saved sources and validated evidence.</p>
  </div>;
}
