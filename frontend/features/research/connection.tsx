import { useState } from "react";
import { Banner, Button } from "@/components/ui";
import { Dialog } from "@/components/dialog";
import type { Cancellation, ProgressConnection } from "./use-research";

export type ResearchRecoveryProps = {
  connection: ProgressConnection;
  lastConfirmedAt: number | null;
  cancellation: Cancellation;
  onReconnect: () => void;
  onHistory: () => void;
  onCancel: () => void;
  canCancel?: boolean;
};

/**
 * Connection status. Healthy progress only keeps a polite live region for screen
 * readers; a visible banner appears when the connection is retrying, paused or
 * has just been restored.
 */
export function ResearchRecovery({
  connection,
  lastConfirmedAt,
  onReconnect,
  onHistory,
}: Pick<ResearchRecoveryProps, "connection" | "lastConfirmedAt" | "onReconnect" | "onHistory">) {
  const unavailable = connection.state === "retrying" || connection.state === "paused";
  const status =
    connection.state === "paused"
      ? "Progress unavailable. Automatic retries paused. Reconnect to check this run."
      : connection.state === "retrying"
        ? "Progress connection lost. Retrying automatically."
        : connection.state === "connecting"
          ? "Connecting to saved progress…"
          : connection.recovered
            ? "Progress connection restored."
            : "Progress is connected.";
  const confirmed =
    lastConfirmedAt === null ? (
      "No progress snapshot confirmed yet."
    ) : (
      <>
        Last confirmed update:{" "}
        <time dateTime={new Date(lastConfirmedAt).toISOString()}>
          {new Date(lastConfirmedAt).toLocaleTimeString()}
        </time>
        . What you see is from that update.
      </>
    );
  return (
    <section className="research-connection" aria-label="Progress connection">
      {unavailable ? (
        <Banner
          tone="warning"
          title={<span role="status" aria-live="polite" aria-atomic="true">{status}</span>}
          action={
            <>
              <Button size="sm" icon="refresh" onClick={onReconnect}>Reconnect</Button>
              <Button size="sm" variant="ghost" onClick={onHistory}>Open History</Button>
            </>
          }
        >
          <p>Research may still be running.</p>
          {connection.error && <p>{connection.error}</p>}
          <p className="progress-received">{confirmed}</p>
        </Banner>
      ) : connection.recovered && connection.state === "connected" ? (
        <Banner tone="success" title={<span role="status" aria-live="polite" aria-atomic="true">{status}</span>}>
          <p className="progress-received">{confirmed}</p>
        </Banner>
      ) : (
        <p className="sr-only" role="status" aria-live="polite" aria-atomic="true">{status}</p>
      )}
    </section>
  );
}

/** Secondary cancel action; the backend must confirm before it is reported as requested. */
export function CancelRun({
  cancellation,
  onCancel,
  canCancel = true,
}: Pick<ResearchRecoveryProps, "cancellation" | "onCancel" | "canCancel">) {
  const [confirming, setConfirming] = useState(false);
  if (!canCancel) return null;
  return (
    <div className="cancel-run">
      <Button
        variant="secondary"
        icon="stop"
        onClick={() => setConfirming(true)}
        disabled={cancellation.state === "sending" || cancellation.state === "requested"}
      >
        {cancellation.state === "sending"
          ? "Sending cancellation…"
          : cancellation.state === "requested"
            ? "Cancellation requested"
            : "Cancel run"}
      </Button>
      <p className="subtle" role="status" aria-live="polite" aria-atomic="true">
        {cancellation.message}
      </p>
      {confirming && (
        <Dialog title="Stop this research?" onClose={() => setConfirming(false)}>
          <p className="muted">
            Work saved so far is kept: sources found, pages read and findings stay in History, and you can resume this run
            later. A request already in progress may finish before the run stops.
          </p>
          <div className="dialog-actions">
            <Button variant="ghost" onClick={() => setConfirming(false)}>Keep researching</Button>
            <Button
              variant="danger"
              onClick={() => {
                setConfirming(false);
                onCancel();
              }}
            >
              Stop research
            </Button>
          </div>
        </Dialog>
      )}
    </div>
  );
}
