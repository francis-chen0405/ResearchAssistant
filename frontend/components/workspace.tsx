import type { ReactNode } from "react";

export function StatusPill({
  children,
  tone = "neutral",
}: {
  children: ReactNode;
  tone?: "neutral" | "support" | "challenge" | "active";
}) {
  return (
    <span className={`status-pill ${tone}`}>
      <i aria-hidden="true" />
      {children}
    </span>
  );
}
