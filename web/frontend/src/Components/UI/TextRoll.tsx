"use client";

import { AnimatePresence, motion, type Variants } from "motion/react";
import { useEffect, useState, type ReactNode } from "react";
import { useReducedMotion } from "../Hooks/useReducedMotion";

export interface TextRollProps {
  children: ReactNode;
  className?: string;
  duration?: number;
  variants?: { enter?: Variants; exit?: Variants };
}

export function TextRoll({ children, className, duration = 0.35, variants }: TextRollProps) {
  const [key, setKey] = useState(0);
  const reducedMotion = useReducedMotion();

  useEffect(() => {
    if (reducedMotion) return;
    setKey(value => value + 1);
  }, [children, reducedMotion]);

  if (reducedMotion) return <span className={className}>{children}</span>;

  const enter = variants?.enter ?? { initial: { rotateX: 90, opacity: 0 }, animate: { rotateX: 0, opacity: 1 } };
  const exit = variants?.exit ?? { initial: { rotateX: 0, opacity: 1 }, animate: { rotateX: -90, opacity: 0 } };

  return (
    <span className={className} style={{ display: "inline-block", perspective: 600 }} aria-live="polite" aria-atomic="true">
      <AnimatePresence mode="wait" initial={false}>
        <motion.span
          key={key}
          style={{ display: "inline-block", transformOrigin: "50% 50%" }}
          initial={enter.initial as never}
          animate={enter.animate as never}
          exit={exit.animate as never}
          transition={{ duration }}
        >
          {children}
        </motion.span>
      </AnimatePresence>
    </span>
  );
}
