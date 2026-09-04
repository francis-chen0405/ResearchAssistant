import type { FormEvent } from "react";

type Props = {
  claim: string;
  acknowledged: boolean;
  busy: boolean;
  signedIn: boolean;
  onClaimChange: (value: string) => void;
  onAcknowledgedChange: (value: boolean) => void;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
  onSignIn: () => void;
  onAdvanced: () => void;
};

export function ResearchComposer({ claim, acknowledged, busy, signedIn, onClaimChange, onAcknowledgedChange, onSubmit, onSignIn, onAdvanced }: Props): React.ReactElement {
  return (
    <form className="composer" onSubmit={onSubmit}>
      <div className="composer-kicker"><span className="signal-orb" /> Public claim workspace</div>
      <label htmlFor="claim">What should we investigate?</label>
      <textarea id="claim" value={claim} onChange={(event) => onClaimChange(event.target.value)} placeholder="Paste a claim worth checking…" rows={3} />
      <label className="check-row"><input type="checkbox" checked={acknowledged} onChange={(event) => onAcknowledgedChange(event.target.checked)} /> <span>I understand this research uses public sources and produces an inspectable evidence trail.</span></label>
      {!signedIn ? <div className="composer-note">Sign in to save your research workspace and reconnect to runs later.</div> : null}
      <div className="composer-footer">
        <button type="button" className="text-button" onClick={onAdvanced}>Advanced controls <span>↗</span></button>
        <button type="submit" className="primary-button" disabled={busy || !signedIn || !claim.trim() || !acknowledged}>{busy ? "Queueing…" : "Start research"}<span>→</span></button>
      </div>
      {!signedIn ? <button type="button" className="inline-link" onClick={onSignIn}>Send me a magic sign-in link</button> : null}
    </form>
  );
}
