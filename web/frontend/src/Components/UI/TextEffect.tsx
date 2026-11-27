"use client";

import { AnimatePresence, motion, type TargetAndTransition, type Transition, type Variant, type Variants } from "motion/react";
import type { CSSProperties, ElementType, ReactNode } from "react";
import { memo } from "react";
import { useReducedMotion } from "../Hooks/useReducedMotion";

export type TextEffectPreset = "blur" | "fade-in-blur" | "scale" | "fade" | "slide";
export type TextEffectPer = "word" | "char" | "line";

export interface TextEffectProps {
  children: ReactNode;
  per?: TextEffectPer;
  as?: ElementType;
  variants?: { container?: Variants; item?: Variants };
  className?: string;
  preset?: TextEffectPreset;
  delay?: number;
  speedReveal?: number;
  speedSegment?: number;
  trigger?: boolean;
  onAnimationComplete?: () => void;
  onAnimationStart?: () => void;
  segmentWrapperClassName?: string;
  containerTransition?: Transition;
  segmentTransition?: Transition;
  style?: CSSProperties;
}

const stagger: Record<TextEffectPer, number> = { char: 0.03, word: 0.05, line: 0.1 };
const containerVariants: Variants = {
  hidden: { opacity: 0 },
  visible: { opacity: 1, transition: { staggerChildren: 0.05 } },
  exit: { transition: { staggerChildren: 0.05, staggerDirection: -1 } },
};
const presets: Record<TextEffectPreset, Variants> = {
  blur: { hidden: { opacity: 0, filter: "blur(12px)" }, visible: { opacity: 1, filter: "blur(0px)" }, exit: { opacity: 0, filter: "blur(12px)" } },
  "fade-in-blur": { hidden: { opacity: 0, y: 20, filter: "blur(12px)" }, visible: { opacity: 1, y: 0, filter: "blur(0px)" }, exit: { opacity: 0, y: 20, filter: "blur(12px)" } },
  scale: { hidden: { opacity: 0, scale: 0 }, visible: { opacity: 1, scale: 1 }, exit: { opacity: 0, scale: 0 } },
  fade: { hidden: { opacity: 0 }, visible: { opacity: 1 }, exit: { opacity: 0 } },
  slide: { hidden: { opacity: 0, y: 20 }, visible: { opacity: 1, y: 0 }, exit: { opacity: 0, y: 20 } },
};
const hasTransition = (variant?: Variant): variant is TargetAndTransition & { transition?: Transition } =>
  Boolean(variant && typeof variant === "object" && "transition" in variant);

const Segment = memo(function Segment({ text, per, variants, wrapperClassName }: {
  text: ReactNode;
  per: TextEffectPer;
  variants: Variants;
  wrapperClassName?: string;
}) {
  const visual = typeof text !== "string" ? (
    <motion.span variants={variants} style={{ display: "inline-block" }}>{text}</motion.span>
  ) : per === "line" ? (
    <motion.span aria-hidden="true" variants={variants} style={{ display: "block" }}>{text || "\u00a0"}</motion.span>
  ) : per === "char" ? (
    <span aria-hidden="true" style={{ display: "inline-block", whiteSpace: "pre" }}>
      {Array.from(text).map((char, index) => (
        <motion.span key={index} variants={variants} style={{ display: "inline-block", whiteSpace: "pre" }}>{char}</motion.span>
      ))}
    </span>
  ) : (
    <motion.span aria-hidden="true" variants={variants} style={{ display: "inline-block", whiteSpace: "pre" }}>{text}</motion.span>
  );

  if (!wrapperClassName) return visual;
  return <span className={wrapperClassName} style={{ display: per === "line" ? "block" : "inline-block" }}>{visual}</span>;
});

export function TextEffect({
  children, per = "word", as = "p", variants, className, preset = "fade", delay = 0,
  speedReveal = 1, speedSegment = 1, trigger = true, onAnimationComplete, onAnimationStart,
  segmentWrapperClassName, containerTransition, segmentTransition, style,
}: TextEffectProps) {
  const reducedMotion = useReducedMotion();
  const segments: ReactNode[] = typeof children === "string"
    ? per === "line" ? children.split("\n") : per === "char" ? Array.from(children) : children.split(/(\s+)/)
    : [children];
  const MotionTag = motion.create(as);
  const customContainer = variants?.container?.visible;
  const customStagger = hasTransition(customContainer) ? customContainer.transition?.staggerChildren : undefined;
  const customDelay = hasTransition(customContainer) ? customContainer.transition?.delayChildren : undefined;
  const itemBase = variants?.item ?? presets[preset];
  const container = variants?.container ?? containerVariants;
  const computedContainer: Variants = {
    ...container,
    visible: { ...container.visible, transition: {
      ...(hasTransition(container.visible) ? container.visible.transition : {}),
      staggerChildren: customStagger ?? stagger[per] / Math.max(speedReveal, 0.01),
      delayChildren: customDelay ?? delay,
      ...containerTransition,
    } },
  };
  const computedItem: Variants = {
    ...itemBase,
    visible: { ...itemBase.visible, transition: { duration: 0.3 / Math.max(speedSegment, 0.01), ...segmentTransition } },
  };

  return (
    <AnimatePresence mode="popLayout">
      {trigger ? (
        <MotionTag
          initial={reducedMotion ? false : "hidden"}
          animate="visible"
          exit="exit"
          variants={computedContainer}
          className={className}
          onAnimationComplete={onAnimationComplete}
          onAnimationStart={onAnimationStart}
          style={style}
        >
          {typeof children === "string" ? <span className="sr-only">{children}</span> : null}
          {segments.map((segment, index) => (
            <Segment
              key={per + "-" + index}
              text={segment}
              per={per}
              variants={computedItem}
              wrapperClassName={segmentWrapperClassName}
            />
          ))}
        </MotionTag>
      ) : null}
    </AnimatePresence>
  );
}
