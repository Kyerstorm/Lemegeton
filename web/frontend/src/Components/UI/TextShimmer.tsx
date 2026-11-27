"use client";

import type { ReactNode } from "react";

export interface TextShimmerProps { children: ReactNode; className?: string; duration?: number; }
export function TextShimmer({ children, className = "", duration = 2 }: TextShimmerProps) {
  return <span className={["text-shimmer", className].filter(Boolean).join(" ")} style={{ animationDuration: duration + "s" }}>{children}</span>;
}
