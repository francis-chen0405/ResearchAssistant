import { motion } from "motion/react";
import type { HistoryItem } from "@/lib/api";
import { readableStage, formatDate } from "../shared/presentation";

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
                {item.status}
              </span>
              <motion.strong layoutId={`claim-${item.run_id}`}>
                {item.raw_claim}
              </motion.strong>
              <span>{readableStage(item.stage)}</span>
              <time>{formatDate(item.updated_at)}</time>
              <b aria-hidden="true">↗</b>
            </motion.button>
          ))
        )}
      </div>
    </motion.section>
  );
}
