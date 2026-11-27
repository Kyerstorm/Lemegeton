"use client";

import { motion } from "motion/react";
import { useReducedMotion } from "../Hooks/useReducedMotion";

export interface StreamProps {
  className?: string;
  density?: number;
}

export function Stream({ className = "", density = 5 }: StreamProps) {
  const reducedMotion = useReducedMotion();
  const lines = Array.from({ length: Math.max(2, Math.min(9, density)) }, (_, index) => index);
  return (
    <div className={"hiw-stream " + className} aria-hidden="true">
      <svg viewBox="0 0 1200 360" preserveAspectRatio="none">
        <defs><linearGradient id="hiw-stream-gradient" x1="0" x2="1"><stop offset="0" stopColor="#777" stopOpacity="0" /><stop offset=".5" stopColor="#ddd" stopOpacity=".42" /><stop offset="1" stopColor="#777" stopOpacity="0" /></linearGradient></defs>
        {lines.map((index) => {
          const y = 44 + index * (272 / Math.max(1, lines.length - 1));
          const path = "M -20 " + y + " C 190 " + (y - 70) + ", 305 " + (y + 85) + ", 520 180 S 925 " + (y - 74) + ", 1220 " + (y + 6);
          return <motion.path key={index} d={path} fill="none" stroke="url(#hiw-stream-gradient)" strokeWidth="1" strokeDasharray="3 11"
            animate={reducedMotion ? { strokeDashoffset: 0, opacity: .18 } : { strokeDashoffset: [0, -180], opacity: [.12, .42, .12] }}
            transition={reducedMotion ? { duration: 0 } : { duration: 18 + index * 2.4, repeat: Infinity, ease: "linear" }} />;
        })}
      </svg>
    </div>
  );
}
