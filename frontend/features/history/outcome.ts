import type { HistoryItem } from "@/lib/api";
import type { Tone } from "@/components/ui";
import { phaseWordOf } from "../research/phases";

export type Outcome = { label: string; tone: Tone; group: "complete" | "stopped" | "running" };

/** One plain outcome per saved run; "completed" and "released" both read Complete. */
export function historyOutcome(status: string): Outcome {
  switch (status) {
    case "completed":
    case "released":
      return { label: "Complete", tone: "success", group: "complete" };
    case "planned":
    case "running":
      return { label: "In progress", tone: "info", group: "running" };
    case "blocked":
      return { label: "Stopped early", tone: "warning", group: "stopped" };
    case "cancelled":
      return { label: "Cancelled", tone: "neutral", group: "stopped" };
    case "interrupted":
      return { label: "Interrupted", tone: "warning", group: "stopped" };
    case "failed":
      return { label: "Failed", tone: "error", group: "stopped" };
    default:
      return { label: "Status not recognized", tone: "neutral", group: "stopped" };
  }
}

/** Where a run that did not complete stopped, in plain words. */
export function historyReason(item: Pick<HistoryItem, "status" | "stage">): string | null {
  const outcome = historyOutcome(item.status);
  if (outcome.group !== "stopped") return null;
  const phase = phaseWordOf(item.stage);
  return phase === null ? "Stopped before completing" : `Stopped during ${phase}`;
}
