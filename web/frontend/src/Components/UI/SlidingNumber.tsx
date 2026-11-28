"use client";

import { AnimatePresence, motion } from "motion/react";
import { useReducedMotion } from "../Hooks/useReducedMotion";

export interface SlidingNumberProps {
  value: number;
  className?: string;
}

export function SlidingNumber({ value, className = "" }: SlidingNumberProps) {
  const formatted = new Intl.NumberFormat("en-US").format(value);
  const reducedMotion = useReducedMotion();

  return (
    <span
      className={className}
      style={{ display: "inline-flex", overflow: "hidden", verticalAlign: "bottom", fontVariantNumeric: "tabular-nums" }}
      aria-label={formatted}
    >
      <span className="sr-only">{formatted}</span>
      {Array.from(formatted).map((char, index) => (
        <span key={index} aria-hidden="true" style={{ display: "inline-block" }}>
          {/\d/.test(char) ? (
            <AnimatePresence mode="popLayout" initial={false}>
              <motion.span
                key={char + "-" + index}
                initial={reducedMotion ? false : { y: "100%", opacity: 0 }}
                animate={{ y: 0, opacity: 1 }}
                exit={{ y: "-100%", opacity: 0 }}
                transition={{ duration: reducedMotion ? 0 : 0.22 }}
                style={{ display: "inline-block" }}
              >
                {char}
              </motion.span>
            </AnimatePresence>
          ) : char}
        </span>
      ))}
    </span>
  );
}
