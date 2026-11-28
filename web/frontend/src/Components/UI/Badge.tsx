import type { ReactNode } from "react";

export interface BadgeProps {
  children: ReactNode;
  tone?: "good" | "bad" | "neutral";
  ok?: boolean;
}

export function Badge({ children, tone = "neutral", ok }: BadgeProps) {
  const resolvedTone = ok === true ? "good" : ok === false ? "bad" : tone;
  const state = resolvedTone === "good" ? "is-good" : resolvedTone === "bad" ? "is-bad" : "is-neutral";
  return <span className={"status-pill " + state}><i aria-hidden="true" />{children}</span>;
}

export const StatusPill = Badge;
export type StatusPillProps = BadgeProps;
