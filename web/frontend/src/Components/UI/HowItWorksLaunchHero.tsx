"use client";

import { motion } from "motion/react";
import { Icon } from "../Icons";
import { GlowEffect } from "./GlowEffect";
import { useReducedMotion } from "../Hooks/useReducedMotion";

export interface LaunchHeroProps {
  title?: string;
  emphasis?: string;
  description?: string;
  primaryLabel?: string;
  primaryHref?: string;
  secondaryLabel?: string;
  secondaryHref?: string;
}

export function LaunchHero({
  title = "More than a bot.",
  emphasis = "A connected system.",
  description = "Lemegeton brings media discovery, shared archives and community activities into Discord — with an optional dashboard for authorised server managers.",
  primaryLabel = "Explore the architecture",
  primaryHref = "#architecture",
  secondaryLabel = "View source",
  secondaryHref = "/github",
}: LaunchHeroProps) {
  const reducedMotion = useReducedMotion();
  const enter = (delay: number) => reducedMotion
    ? { initial: false as const, animate: { opacity: 1, y: 0, filter: "blur(0px)" } }
    : { initial: { opacity: 0, y: 14, filter: "blur(8px)" }, animate: { opacity: 1, y: 0, filter: "blur(0px)" }, transition: { duration: 0.9, delay, ease: [0.2, 0.8, 0.2, 1] as const } };

  return (
    <div className="hiw-launch-hero">
      <div className="hiw-launch-glow"><GlowEffect colors={["#fff", "#555", "#fff"]} mode="rotate" blur="strong" duration={22} scale={1.2} /></div>
      <motion.p className="hiw-eyebrow hiw-hero-eyebrow" {...enter(0.05)}>
        <span className="hiw-live-mark" /> MULTI-GUILD DISCORD BOT <span className="hiw-eyebrow-divider">/</span> SYSTEM OVERVIEW
      </motion.p>
      <motion.h1 {...enter(0.16)}>{title}<br /><span>{emphasis}</span></motion.h1>
      <motion.p className="hiw-hero-copy" {...enter(0.3)}>{description}</motion.p>
      <motion.div className="hiw-hero-actions" {...enter(0.42)}>
        <a className="hiw-button hiw-button-primary" href={primaryHref}>{primaryLabel} <Icon name="chevron-down" size={15} /></a>
        <a className="hiw-button hiw-button-quiet" href={secondaryHref} target={secondaryHref.startsWith("http") || secondaryHref === "/github" ? "_blank" : undefined} rel="noreferrer">{secondaryLabel} <Icon name="arrow-up-right" size={14} /></a>
      </motion.div>
      <div className="hiw-hero-meta"><span>01 / DISCOVER</span><span>02 / SHARE</span><span>03 / PARTICIPATE</span></div>
    </div>
  );
}
