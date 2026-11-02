import { motion } from "motion/react";
import type { HistoryItem } from "@/lib/api";
import { formatDate } from "../shared/presentation";

const statuses: Record<string, string> = {
  planned: "Planned", running: "Running", completed: "Completed", released: "Released",
  blocked: "Stopped", cancelled: "Cancelled", failed: "Failed", interrupted: "Interrupted",
};
const stages: Record<string, string> = {
  claim_planner: "Planning", discovery: "Finding sources", acquisition: "Reading sources",
  gap_analysis: "Checking gaps", adaptive_search: "Follow-up search", source_selection: "Selecting sources",
  deep_analysis: "Assessing evidence", review: "Review", synthesis: "Preparing the brief",
  evidence_analyst: "Assessing evidence", evidence_admission: "Assessing evidence",
  gap_reconciliation: "Checking gaps", statement_reviewer: "Review", claim_ledger: "Review",
  debate_synthesizer: "Preparing the brief", final_renderer_validator: "Preparing the brief",
};

export function HistoryView({
  items,
  loading,
  onOpen,
}: {
  items: HistoryItem[];
  loading: boolean;
  onOpen: (item: HistoryItem) => void;
}) {
  return (
    <motion.section
      className="history-view"
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0 }}
    >
      <div className="history-heading">
        <p className="eyebrow">Persisted locally</p>
        <h1>Past research</h1>
        <p>
          Return to an earlier evidence trail without starting the work again.
        </p>
      </div>
      <div className="history-list">
        {loading ? (
          <p className="history-empty">Opening the local archive…</p>
        ) : items.length === 0 ? (
          <p className="history-empty">
            Your saved research will appear here. Start a question to build your
            first evidence trail.
          </p>
        ) : (
          items.map((item, index) => (
            <motion.button
              type="button"
              onClick={() => onOpen(item)}
              key={item.run_id}
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: index * 0.035 }}
            >
              <span className={`history-status ${item.status}`}>
                {statuses[item.status] ?? "Status not recognized"}
              </span>
              <motion.strong layoutId={`claim-${item.run_id}`}>
                {item.raw_claim}
              </motion.strong>
              <span>{stages[item.stage] ?? "Research stage not recognized"}</span>
              <time>{formatDate(item.updated_at)}</time>
              <b aria-hidden="true">↗</b>
            </motion.button>
          ))
        )}
      </div>
    </motion.section>
  );
}
