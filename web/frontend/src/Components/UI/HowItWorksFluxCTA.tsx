"use client";

import { useEffect } from "react";
import { animate, motion, useMotionValue, useSpring, useTransform } from "motion/react";
import { Icon } from "../Icons";
import { useReducedMotion } from "../Hooks/useReducedMotion";

export interface FluxCTAProps {
  title?: string;
  emphasis?: string;
  description?: string;
  primaryLabel?: string;
  primaryHref?: string;
  secondaryLabel?: string;
  secondaryHref?: string;
}

export function FluxCTA({
  title = "Understand the system.",
  emphasis = "Help make it better.",
  description = "Explore the code, review the documentation or report a reproducible issue through GitHub.",
  primaryLabel = "Explore GitHub",
  primaryHref = "/github",
  secondaryLabel = "Report an issue",
  secondaryHref = "/issues",
}: FluxCTAProps) {
  const reducedMotion = useReducedMotion();
  const angle = useMotionValue(0);
  const gradientIndex = useMotionValue(0);
  const smoothAngle = useSpring(angle, { stiffness: 28, damping: 20 });
  const smoothIndex = useSpring(gradientIndex, { stiffness: 15, damping: 15 });
  const greys = [
    ["#151515", "#292929", "#444"],
    ["#202020", "#353535", "#555"],
    ["#111", "#262626", "#3b3b3b"],
    ["#1b1b1b", "#303030", "#4b4b4b"],
  ];
  const mix = (start: string, end: string, progress: number) => {
    const a = parseInt(start.slice(1), 16);
    const b = parseInt(end.slice(1), 16);
    const channel = (shift: number) => Math.round(((a >> shift) & 255) + ((((b >> shift) & 255) - ((a >> shift) & 255)) * progress));
    return "rgb(" + channel(16) + ", " + channel(8) + ", " + channel(0) + ")";
  };
  const background = useTransform([smoothAngle, smoothIndex], (values: number[]) => {
    const raw = Math.floor(values[1]);
    const index = ((raw % greys.length) + greys.length) % greys.length;
    const next = (index + 1) % greys.length;
    const t = Math.max(0, Math.min(1, values[1] - raw));
    return "linear-gradient(" + values[0] + "deg, " + mix(greys[index][0], greys[next][0], t) + " 10%, " + mix(greys[index][1], greys[next][1], t) + " 60%, " + mix(greys[index][2], greys[next][2], t) + " 100%)";
  });
  const buttonBackground = useTransform(smoothIndex, (value: number) => {
    const raw = Math.floor(value);
    const index = ((raw % greys.length) + greys.length) % greys.length;
    const next = (index + 1) % greys.length;
    const t = Math.max(0, Math.min(1, value - raw));
    return "linear-gradient(135deg, " + mix(greys[index][0], greys[next][0], t) + ", " + mix(greys[index][2], greys[next][2], t) + ")";
  });

  useEffect(() => {
    if (reducedMotion) return;
    const rotate = animate(angle, 360, { duration: 18, ease: "linear", repeat: Infinity });
    const colours = animate(gradientIndex, greys.length, { duration: greys.length * 8, ease: "linear", repeat: Infinity });
    return () => { rotate.stop(); colours.stop(); };
  }, [angle, gradientIndex, reducedMotion]);

  return (
    <motion.section className="hiw-flux-cta" style={reducedMotion ? undefined : { background }}>
      <div className="hiw-flux-grid" aria-hidden="true" />
      <p className="hiw-eyebrow">OPEN SOURCE / COMMUNITY BUILT</p>
      <h2>{title}<br /><span>{emphasis}</span></h2>
      <p className="hiw-flux-description">{description}</p>
      <div className="hiw-hero-actions">
        <motion.a className="hiw-button hiw-flux-primary" href={primaryHref} target="_blank" rel="noreferrer"
          style={reducedMotion ? undefined : { background: buttonBackground }}>
          {primaryLabel} <Icon name="arrow-up-right" size={14} />
        </motion.a>
        <a className="hiw-button hiw-button-quiet" href={secondaryHref} target="_blank" rel="noreferrer">{secondaryLabel} <Icon name="arrow-up-right" size={14} /></a>
      </div>
    </motion.section>
  );
}
