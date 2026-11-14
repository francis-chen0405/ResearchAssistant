import { motion } from "motion/react";
import { useState } from "react";
import type { HistoryItem } from "@/lib/api";
import { Button, Chip, EmptyState, Skeleton } from "@/components/ui";
import { Icon } from "@/components/icons";
import { formatDate } from "../shared/presentation";
import { historyOutcome, historyReason } from "./outcome";

const filters = [
  { id: "all", label: "All" },
  { id: "complete", label: "Complete" },
  { id: "stopped", label: "Stopped or failed" },
  { id: "running", label: "In progress" },
] as const;
type Filter = (typeof filters)[number]["id"];

export function HistoryView({
  items,
  loading,
  onOpen,
  onNew,
}: {
  items: HistoryItem[];
  loading: boolean;
  onOpen: (item: HistoryItem) => void;
  onNew?: () => void;
}) {
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState<Filter>("all");
  const visible = items.filter(
    (item) =>
      (filter === "all" || historyOutcome(item.status).group === filter) &&
      item.raw_claim.toLowerCase().includes(query.trim().toLowerCase()),
  );
  return (
    <motion.section className="page history" initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}>
      <header className="page-header">
        <h1>History</h1>
        <p>Open earlier research without running it again. Saved runs are read only.</p>
      </header>
      {items.length > 0 && (
        <div className="history-tools">
          <label className="search-field">
            <Icon name="search" />
            <span className="sr-only">Search history</span>
            <input type="search" placeholder="Search claims" value={query} onChange={(event) => setQuery(event.target.value)} />
          </label>
          <div className="segmented" role="group" aria-label="Filter by outcome">
            {filters.map((item) => (
              <button type="button" key={item.id} aria-pressed={filter === item.id} onClick={() => setFilter(item.id)}>
                {item.label}
              </button>
            ))}
          </div>
        </div>
      )}
      {loading && !items.length ? (
        <div className="history-list" aria-busy="true">
          <p className="sr-only" role="status">Loading history…</p>
          {[0, 1, 2].map((index) => <div className="history-row" key={index}><Skeleton lines={2} /></div>)}
        </div>
      ) : items.length === 0 ? (
        <EmptyState
          icon="history"
          title="Your saved research will appear here."
          action={onNew && <Button variant="primary" icon="plus" onClick={onNew}>Start new research</Button>}
        >
          Each run is saved automatically, including runs that stop early.
        </EmptyState>
      ) : visible.length === 0 ? (
        <EmptyState icon="search" title="No research matches">Try another search or filter.</EmptyState>
      ) : (
        <ul className="history-list">
          {visible.map((item) => {
            const outcome = historyOutcome(item.status);
            const reason = historyReason(item);
            return (
              <li key={item.run_id} className="history-row">
                <button type="button" className="history-open" onClick={() => onOpen(item)}>
                  <motion.span className="history-claim" layoutId={`claim-${item.run_id}`}>{item.raw_claim}</motion.span>
                  <span className="history-meta">
                    <Chip tone={outcome.tone}>{outcome.label}</Chip>
                    {reason && <span>{reason}</span>}
                    <time dateTime={item.updated_at}>{formatDate(item.updated_at)}</time>
                  </span>
                </button>
                {outcome.group === "stopped" && (
                  <Button size="sm" variant="secondary" icon="refresh" onClick={() => onOpen(item)}>
                    Resume or retry
                  </Button>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </motion.section>
  );
}
