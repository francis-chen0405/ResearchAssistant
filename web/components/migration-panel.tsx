"use client";

import { useState } from "react";
import type { MigrationResult } from "@/lib/hosted-api";

type Props = { open: boolean; onClose: () => void; onImport: (bundle: unknown) => Promise<MigrationResult> };

export function MigrationPanel({ open, onClose, onImport }: Props): React.ReactElement | null {
  const [message, setMessage] = useState<string | null>(null);
  if (!open) return null;
  const handleFile = async (file: File | undefined) => { if (!file) return; try { const result = await onImport(JSON.parse(await file.text())); setMessage(`${result.imported} history records imported; ${result.history_only} remain history-only.`); } catch (error) { setMessage(error instanceof Error ? error.message : "That migration file could not be read."); } };
  return <div className="panel-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}><aside className="side-panel" aria-label="History migration"><button className="close-button" type="button" onClick={onClose} aria-label="Close migration">×</button><p className="eyebrow">Bring your archive</p><h2>Keep the questions you’ve already asked.</h2><p className="muted">Choose a fingerprinted history bundle created by the local migration helper. The original source is read-only and incomplete runs are imported as history, never resumed.</p><label className="file-picker">Choose migration bundle<input type="file" accept="application/json" onChange={(event) => void handleFile(event.target.files?.[0])} /></label>{message ? <p className="notice-inline">{message}</p> : null}</aside></div>;
}
