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

export function ResearchRecovery({
  connection,
  lastConfirmedAt,
  cancellation,
  onReconnect,
  onHistory,
  onCancel,
  canCancel = true,
}: ResearchRecoveryProps) {
  const unavailable =
    connection.state === "retrying" || connection.state === "paused";
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
  return (
    <section className="research-connection" aria-label="Progress connection">
      <p role="status" aria-live="polite" aria-atomic="true">
        {status}
      </p>
      {unavailable && (
        <>
          <p>Research may still be running.</p>
          <p>{connection.error}</p>
        </>
      )}
      <p className="progress-received">
        {lastConfirmedAt === null ? (
          "No progress snapshot confirmed yet."
        ) : (
          <>
            Last confirmed update:{" "}
            <time dateTime={new Date(lastConfirmedAt).toISOString()}>
              {new Date(lastConfirmedAt).toLocaleString()}
            </time>
            . Displayed progress is from that update.
          </>
        )}
      </p>
      <div className="connection-actions">
        <button type="button" onClick={onReconnect} disabled={!unavailable}>
          Reconnect
        </button>
        <button type="button" onClick={onHistory}>Open History</button>
        {canCancel && (
          <button
            type="button"
            onClick={onCancel}
            disabled={
              cancellation.state === "sending" || cancellation.state === "requested"
            }
          >
            {cancellation.state === "sending"
              ? "Sending cancellation…"
              : cancellation.state === "requested"
                ? "Cancellation requested"
                : "Cancel run"}
          </button>
        )}
      </div>
      <p role="status" aria-live="polite" aria-atomic="true">
        {cancellation.message}
      </p>
    </section>
  );
}
