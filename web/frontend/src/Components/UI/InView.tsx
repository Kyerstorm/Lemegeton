"use client";

import { motion, useInView, type Transition, type Variants } from "motion/react";
import { useRef, type ReactNode } from "react";
import { useReducedMotion } from "../Hooks/useReducedMotion";

export interface InViewProps {
  children: ReactNode;
  variants?: Variants;
  transition?: Transition;
  viewOptions?: { once?: boolean; amount?: number | "some" | "all"; margin?: NonNullable<Parameters<typeof useInView>[1]>["margin"] };
  className?: string;
}

export function InView({
  children,
  variants = { hidden: { opacity: 0, y: 20 }, visible: { opacity: 1, y: 0 } },
  transition = { duration: 0.4, ease: "easeOut" },
  viewOptions,
  className,
}: InViewProps) {
  const ref = useRef<HTMLDivElement>(null);
  const reducedMotion = useReducedMotion();
  const inView = useInView(ref, {
    once: viewOptions?.once ?? true,
    amount: viewOptions?.amount ?? "some",
    margin: viewOptions?.margin,
  });
  const visible = reducedMotion || inView;

  return (
    <motion.div
      ref={ref}
      initial={reducedMotion ? false : "hidden"}
      animate={visible ? "visible" : "hidden"}
      variants={variants}
      transition={reducedMotion ? { duration: 0 } : transition}
      className={className}
    >
      {children}
    </motion.div>
  );
}
