"use client";
import { ReactNode, useEffect, useId, useRef } from "react";

export function Dialog({ title, onClose, children, wide = false }: { title: string; onClose: () => void; children: ReactNode; wide?: boolean }) {
  const ref = useRef<HTMLDialogElement>(null);
  const titleId = useId();
  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null;
    const dialog = ref.current;
    dialog?.showModal();
    return () => { dialog?.close(); previous?.focus(); };
  }, []);
  return <dialog ref={ref} className={`modal native-dialog ${wide ? "wide-dialog" : ""}`} aria-labelledby={titleId} onKeyDown={event => {
    if (event.key !== "Tab") return;
    const targets = Array.from(event.currentTarget.querySelectorAll<HTMLElement>('button:not(:disabled), input:not(:disabled), select:not(:disabled), textarea:not(:disabled), a[href], summary, [tabindex="0"]')).filter(element => element.checkVisibility());
    if (!targets.length) { event.preventDefault(); return; }
    event.preventDefault();
    const index = targets.indexOf(document.activeElement as HTMLElement);
    targets[(index + (event.shiftKey ? -1 : 1) + targets.length) % targets.length].focus();
  }} onCancel={(event) => { event.preventDefault(); onClose(); }} onClick={event => { if (event.target === event.currentTarget) { const rect = event.currentTarget.getBoundingClientRect(); if (event.clientX < rect.left || event.clientX > rect.right || event.clientY < rect.top || event.clientY > rect.bottom) onClose(); } }}><button autoFocus type="button" className="close-button" aria-label="Close" onClick={onClose}>×</button><p className="eyebrow">Your local workspace</p><h2 id={titleId}>{title}</h2>{children}</dialog>;
}
