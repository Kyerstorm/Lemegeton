"use client";

import { motion } from "motion/react";
import { useReducedMotion } from "../Hooks/useReducedMotion";

export interface TextShimmerWaveProps {
  children: string;
  className?: string;
  duration?: number;
  spread?: number;
  zDistance?: number;
  scaleDistance?: number;
  rotateYDistance?: number;
}

export function TextShimmerWave({ children, className = "", duration = 1.5, spread = 1, zDistance = 1, scaleDistance = 1.04, rotateYDistance = 12 }: TextShimmerWaveProps) {
  const reducedMotion = useReducedMotion();
  if (reducedMotion) return <span className={className}>{children}</span>;

  return (
    <span className={className} aria-label={children}>
      {Array.from(children).map((char, index) => (
        <motion.span
          key={index}
          aria-hidden="true"
          style={{ display: "inline-block" }}
          animate={{ opacity: [0.65, 1, 0.65], y: [0, -2 * zDistance, 0], scale: [1, scaleDistance, 1], rotateY: [0, rotateYDistance, 0] }}
          transition={{ duration, delay: index * 0.035 * spread, repeat: Infinity, ease: "easeInOut" }}
        >
          {char === " " ? "\u00a0" : char}
        </motion.span>
      ))}
    </span>
  );
}
