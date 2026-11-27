"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { motion } from "../DesignSystem/Motion";
import { useReducedMotion } from "../Hooks/useReducedMotion";

export interface AnimatedNumberProps {
  value: number | null | undefined;
  prefix?: string;
  suffix?: string;
  className?: string;
  duration?: number;
  maximumFractionDigits?: number;
}

export function AnimatedNumber({
  value,
  prefix = "",
  suffix = "",
  className = "",
  duration = motion.durationMs.count,
  maximumFractionDigits = 0,
}: AnimatedNumberProps) {
  const target = value != null && Number.isFinite(value) ? value : null;
  const [display, setDisplay] = useState(0);
  const reducedMotion = useReducedMotion();
  const current = useRef(0);
  const formatter = useMemo(
    () => new Intl.NumberFormat("en-US", { maximumFractionDigits }),
    [maximumFractionDigits],
  );

  useEffect(() => {
    if (target === null) {
      current.current = 0;
      setDisplay(0);
      return;
    }

    if (reducedMotion || duration <= 0) {
      current.current = target;
      setDisplay(target);
      return;
    }

    const start = current.current;
    const startedAt = performance.now();
    let frame = 0;

    const tick = (now: number) => {
      const progress = Math.min(1, (now - startedAt) / duration);
      const eased = 1 - Math.pow(1 - progress, 3);
      const next = start + (target - start) * eased;
      current.current = progress === 1 ? target : next;
      setDisplay(current.current);

      if (progress < 1) frame = requestAnimationFrame(tick);
    };

    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [target, reducedMotion, duration]);

  const label = target === null
    ? "Unavailable"
    : prefix + formatter.format(target) + suffix;

  return (
    <span
      className={["font-numeric", className].filter(Boolean).join(" ")}
      aria-label={label}
      aria-live="off"
    >
      {target === null ? "—" : prefix + formatter.format(display) + suffix}
    </span>
  );
}
