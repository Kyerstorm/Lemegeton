"use client";

import { motion, useScroll, useSpring } from "motion/react";
import type { RefObject } from "react";
import { useReducedMotion } from "../Hooks/useReducedMotion";

export interface ScrollProgressProps {
  containerRef?: RefObject<HTMLElement | null>;
  className?: string;
  springOptions?: { stiffness?: number; damping?: number; mass?: number };
}

export function ScrollProgress({ containerRef, className = "", springOptions = { stiffness: 280, damping: 28, mass: 0.3 } }: ScrollProgressProps) {
  const { scrollYProgress } = useScroll({ container: containerRef });
  const reducedMotion = useReducedMotion();
  const scaleX = useSpring(scrollYProgress, springOptions);

  return <motion.div className={className} style={{ scaleX: reducedMotion ? scrollYProgress : scaleX, transformOrigin: "0% 50%" }} />;
}
