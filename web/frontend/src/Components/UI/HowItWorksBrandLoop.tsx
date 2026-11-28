"use client";

import { motion } from "motion/react";
import { useReducedMotion } from "../Hooks/useReducedMotion";

export interface BrandLoopProps {
  items?: string[];
  label?: string;
  duration?: number;
  direction?: "left" | "right";
}

const stack = ["TypeScript", "discord.js", "Next.js", "React", "Rust", "Axum", "libSQL", "RocksDB"];

export function BrandLoop({
  items = stack,
  label = "THE CURRENT V3 STACK",
  duration = 34,
  direction = "left",
}: BrandLoopProps) {
  const reducedMotion = useReducedMotion();
  const allItems = [...items, ...items];
  return (
    <section className="hiw-brand-loop-section" aria-label={label}>
      <div className="hiw-brand-loop-heading"><span>{label}</span><span>BOT · DASHBOARD · STORAGE</span></div>
      <div className="hiw-brand-loop">
        <motion.div className="hiw-brand-track"
          animate={reducedMotion ? undefined : { x: direction === "left" ? ["0%", "-50%"] : ["-50%", "0%"] }}
          transition={reducedMotion ? undefined : { duration, ease: "linear", repeat: Infinity }}>
          {allItems.map((item, index) => <span key={item + "-" + index}>{item}</span>)}
        </motion.div>
      </div>
    </section>
  );
}
