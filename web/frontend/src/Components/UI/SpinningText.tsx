"use client";

import { motion, type Variants } from "motion/react";
import { useId } from "react";
import { useReducedMotion } from "../Hooks/useReducedMotion";

export interface SpinningTextProps {
  children: string;
  radius?: number;
  fontSize?: number;
  className?: string;
  variants?: { container?: Variants; item?: Variants };
  duration?: number;
}

export function SpinningText({ children, radius = 5, fontSize = 1, className = "", variants, duration = 12 }: SpinningTextProps) {
  const pathId = "spinning-text-" + useId().replace(/:/g, "");
  const pathRadius = Math.min(45, Math.max(20, 35 + radius));
  const reducedMotion = useReducedMotion();

  return (
    <motion.svg
      viewBox="0 0 100 100"
      className={className}
      role="img"
      aria-label={children}
      variants={variants?.container}
      initial={reducedMotion ? false : variants?.container ? "hidden" : false}
      animate={reducedMotion ? { rotate: 0 } : variants?.container ? "visible" : { rotate: 360 }}
      transition={reducedMotion ? { duration: 0 } : { duration, repeat: Infinity, ease: "linear" }}
    >
      <defs>
        <path
          id={pathId}
          d={`M 50,50 m -${pathRadius},0 a ${pathRadius},${pathRadius} 0 1,1 ${pathRadius * 2},0 a ${pathRadius},${pathRadius} 0 1,1 -${pathRadius * 2},0`}
        />
      </defs>
      <text fill="currentColor" fontSize={fontSize * 5} letterSpacing="2">
        <textPath href={"#" + pathId}>{children}</textPath>
      </text>
    </motion.svg>
  );
}
