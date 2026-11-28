"use client";

import { useRef, type CSSProperties, type PointerEvent } from "react";
import { motion, useMotionTemplate, useMotionValue } from "motion/react";

export interface SpotlightGridProps {
  className?: string;
  spotlightSize?: number;
  gap?: number;
  dotSize?: number;
  hoverDotSize?: number;
}

export function SpotlightGrid({
  className = "",
  spotlightSize = 190,
  gap = 24,
  dotSize = 1,
  hoverDotSize = 2,
}: SpotlightGridProps) {
  const ref = useRef<HTMLDivElement>(null);
  const x = useMotionValue(0);
  const y = useMotionValue(0);
  const mask = useMotionTemplate`radial-gradient(circle ${spotlightSize}px at ${x}px ${y}px, #000 0%, transparent 100%)`;
  const baseStyle = {
    backgroundImage: "radial-gradient(rgba(255,255,255,.25) var(--dot-size), transparent calc(var(--dot-size) + .6px))",
    backgroundSize: gap + "px " + gap + "px",
    "--dot-size": dotSize + "px",
  } as unknown as CSSProperties;
  const hoverStyle = {
    backgroundImage: "radial-gradient(rgba(255,255,255,.86) var(--hover-dot-size), transparent calc(var(--hover-dot-size) + .7px))",
    backgroundSize: gap + "px " + gap + "px",
    "--hover-dot-size": hoverDotSize + "px",
    maskImage: mask,
    WebkitMaskImage: mask,
  } as unknown as CSSProperties;

  const onPointerMove = (event: PointerEvent<HTMLDivElement>) => {
    if (event.pointerType === "touch" || !ref.current) return;
    const rect = ref.current.getBoundingClientRect();
    x.set(event.clientX - rect.left);
    y.set(event.clientY - rect.top);
  };

  return (
    <div ref={ref} className={"hiw-spotlight " + className} aria-hidden="true" onPointerMove={onPointerMove}>
      <div className="hiw-spotlight-base" style={baseStyle} />
      <motion.div className="hiw-spotlight-focus" style={hoverStyle} />
    </div>
  );
}
