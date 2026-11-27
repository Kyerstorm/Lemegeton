"use client";

import { ThinkingOrb } from "thinking-orbs";

export type ActivityOrbState =
  | "working"
  | "searching"
  | "solving"
  | "listening"
  | "connecting"
  | "weaving"
  | "composing"
  | "breathing"
  | "shaping";

export function ActivityOrb({
  label,
  state = "working",
  size = 20,
  speed = 1,
  dark = true,
  paused = false,
}: {
  label: string;
  state?: ActivityOrbState;
  size?: 20 | 64;
  speed?: number;
  dark?: boolean;
  paused?: boolean;
}) {
  return (
    <span className="activity-orb" role="status">
      <span className="sr-only">{label}</span>
      <ThinkingOrb state={state} size={size} speed={speed} theme={dark ? "dark" : "light"} paused={paused} />
    </span>
  );
}
