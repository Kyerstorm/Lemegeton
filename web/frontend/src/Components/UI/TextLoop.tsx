"use client";

import { AnimatePresence, motion, type Transition, type Variants } from "motion/react";
import { useEffect, useState, type ReactNode } from "react";
import { useReducedMotion } from "../Hooks/useReducedMotion";

export interface TextLoopProps {
  children: ReactNode[];
  interval?: number;
  transition?: Transition;
  variants?: Variants;
  className?: string;
  onIndexChange?: (index: number) => void;
}

export function TextLoop({ children, interval = 2, transition = { duration: 0.3 }, variants, className, onIndexChange }: TextLoopProps) {
  const [index, setIndex] = useState(0);
  const reducedMotion = useReducedMotion();

  useEffect(() => {
    if (reducedMotion || children.length < 2) return;
    const timer = window.setInterval(() => setIndex(current => {
      const next = (current + 1) % children.length;
      onIndexChange?.(next);
      return next;
    }), Math.max(interval, 0.25) * 1000);
    return () => window.clearInterval(timer);
  }, [children.length, interval, onIndexChange, reducedMotion]);

  const motionVariants = variants ?? {
    initial: { opacity: 0, y: 12, filter: "blur(4px)" },
    animate: { opacity: 1, y: 0, filter: "blur(0px)" },
    exit: { opacity: 0, y: -12, filter: "blur(4px)" },
  };

  if (reducedMotion) return <span className={className}>{children[0]}</span>;

  return (
    <span className={className} aria-live="polite" aria-atomic="true">
      <AnimatePresence mode="wait" initial={false}>
        <motion.span
          key={index}
          style={{ display: "inline-block" }}
          variants={motionVariants}
          initial="initial"
          animate="animate"
          exit="exit"
          transition={transition}
        >
          {children[index]}
        </motion.span>
      </AnimatePresence>
    </span>
  );
}
