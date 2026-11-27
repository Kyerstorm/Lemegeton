"use client";

import { motion } from "motion/react";
import { useReducedMotion } from "../Hooks/useReducedMotion";

export interface GlowEffectProps {
  colors?: string[];
  mode?: "rotate" | "pulse" | "colorShift";
  blur?: "soft" | "medium" | "strong";
  duration?: number;
  scale?: number;
  className?: string;
}

export function GlowEffect({
  colors = ["#ffffff", "#888888", "#ffffff"],
  mode = "rotate",
  blur = "medium",
  duration = 4,
  scale = 1,
  className = "",
}: GlowEffectProps) {
  const reducedMotion = useReducedMotion();
  const gradient = `conic-gradient(from 0deg, ${colors.join(", ")}, ${colors[0]})`;

  return (
    <motion.div
      aria-hidden="true"
      className={className}
      style={{
        position: "absolute",
        inset: 0,
        borderRadius: "inherit",
        pointerEvents: "none",
        zIndex: 0,
        background: gradient,
        filter: `blur(${blur === "soft" ? 12 : blur === "strong" ? 36 : 22}px)`,
        scale,
        opacity: 0.7,
      }}
      animate={reducedMotion ? { opacity: 0.42 } : mode === "pulse" ? { opacity: [0.35, 0.8, 0.35] } : { rotate: mode === "colorShift" ? [0, 180, 360] : 360 }}
      transition={reducedMotion ? { duration: 0 } : { duration, repeat: Infinity, ease: "linear" }}
    />
  );
}
