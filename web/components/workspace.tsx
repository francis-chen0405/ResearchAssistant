"use client";

import { ReactNode, useEffect, useRef, useState, useSyncExternalStore } from "react";
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

const previewSequence = [0, 1, 2, 3, 4, 1, 2, 3];
const motionPreference = "(prefers-reduced-motion: reduce)";
function subscribeMotion(onChange: () => void) {
  const media = window.matchMedia(motionPreference);
  media.addEventListener("change", onChange);
  return () => media.removeEventListener("change", onChange);
}

export function ProductPreview() {
  const [scene, setScene] = useState(0);
  const [paused, setPaused] = useState(false);
  const wrapper = useRef<HTMLDivElement>(null);
  const reducedMotion = useSyncExternalStore(subscribeMotion, () => window.matchMedia(motionPreference).matches, () => false);
  const step = reducedMotion ? 3 : previewSequence[scene];
  useEffect(() => {
    if (reducedMotion || paused) return;
    const timer = window.setInterval(() => {
      if (!document.hidden) setScene(current => (current + 1) % previewSequence.length);
    }, 3600);
    return () => window.clearInterval(timer);
  }, [reducedMotion, paused]);
  const isError = step === 4;
  return <div className="preview-wrap" ref={wrapper} data-preview-step={step}
    onMouseEnter={() => setPaused(true)}
    onMouseLeave={() => setPaused(Boolean(wrapper.current?.contains(document.activeElement)))}
    onFocus={() => setPaused(true)}
    onBlur={event => { if (!event.currentTarget.contains(event.relatedTarget) && !event.currentTarget.matches(":hover")) setPaused(false); }}>
    <span className="floating-label label-source" aria-hidden="true">↗ Follow the source</span>
    <span className="floating-label label-finding" aria-hidden="true">✓ Keep the context</span>
    <WorkspaceFrame title="Research in motion" example status={<StatusPill>Example</StatusPill>}>
      <div className="workspace-topline"><span className="workspace-kicker">RESEARCH NOTEBOOK</span><StatusPill tone={isError ? "challenge" : step === 3 ? "support" : "active"}>{previewStates[step]}</StatusPill></div>
      <div className="preview-primary"><h2>{previewQuestion}</h2>
        <div className="preview-config"><span className="preview-directions"><StatusPill tone="support">+ Support</StatusPill><StatusPill tone="challenge">− Challenge</StatusPill></span><span>Standard research<strong>$0.20 budget</strong></span></div>
        <ProgressPath labels={["Preparing", "Finding evidence", "Checking sources", "Synthesis"]} current={isError ? 1 : step} />
      </div>
      <div className="preview-scene" key={scene}>
        <div className="preview-evidence"><div className="evidence-stack-heading"><span>Evidence collected</span><b>{step === 0 ? "00" : step === 1 || isError ? "01" : "02"}</b></div>
          {step === 0 ? <div className="evidence-placeholder"><span aria-hidden="true">↗</span><h3>Every finding starts with a source.</h3><div className="placeholder-lines" aria-hidden="true"><i /><i /><i /></div></div> : previewEvidence.slice(0, step === 1 || isError ? 1 : 2).map(item => <EvidenceTile key={item.title} {...item} sourceLabel={item.kind} />)}
        </div>
        <div className={`preview-conclusion ${step === 3 ? "complete" : ""}`}><span className="workspace-kicker">{isError ? "RECONNECTING" : step === 3 ? "THE TAKEAWAY" : "EVIDENCE TRAIL"}</span><p>{isError ? "Connection interrupted. Keeping collected evidence and trying again…" : step === 3 ? "Greener streets may help, with important local differences. The finding and its limits belong together." : step === 0 ? "Preparing the question and finding a starting point." : "Checking exact passages and keeping both sides in view."}</p></div>
      </div>
      <div className="preview-budget"><span>Example usage</span><strong>{step === 0 ? "$0.00" : step === 1 || isError ? "$0.03" : "$0.08"}<small> / $0.20</small></strong><progress max={20} value={step === 0 ? 0 : step === 1 || isError ? 3 : 8} /></div>
    </WorkspaceFrame>
  </div>;
}
