"use client";

import { useEffect, useState } from "react";
import { motion } from "motion/react";
import { Icon, type IconName } from "../Icons";
import { useReducedMotion } from "../Hooks/useReducedMotion";

export interface PipelineStage {
  id: string;
  title: string;
  description: string;
  icon: IconName;
}
export interface PipelineProps {
  source?: PipelineStage;
  gate?: PipelineStage;
  destinations?: PipelineStage[];
  particleCount?: number;
  particleSpeed?: number;
}

const destinationsDefault: PipelineStage[] = [
  { id: "guild-api", title: "Approved API", description: "Scoped dashboard operation", icon: "shield-check" },
  { id: "bot-bridge", title: "Private bot bridge", description: "Only when the running bot is needed", icon: "activity" },
  { id: "storage", title: "Shared storage", description: "Same authoritative libSQL store", icon: "database" },
];

export function Pipeline({
  source = { id: "browser", title: "Browser", description: "Authorised manager session", icon: "home" },
  gate = { id: "rust", title: "Rust / Axum", description: "OAuth, session, CSRF and guild checks", icon: "shield-check" },
  destinations = destinationsDefault,
  particleCount = 3,
  particleSpeed = 4,
}: PipelineProps) {
  const [activeIndex, setActiveIndex] = useState(0);
  const reducedMotion = useReducedMotion();

  useEffect(() => {
    if (reducedMotion) return;
    const interval = window.setInterval(() => setActiveIndex((value) => (value + 1) % destinations.length), 3600);
    return () => window.clearInterval(interval);
  }, [destinations.length, reducedMotion]);

  const paths = [
    "M 187 178 L 374 178",
    "M 552 178 L 570 178",
    "M 570 178 C 650 178, 650 70, 760 70",
    "M 570 178 L 760 178",
    "M 570 178 C 650 178, 650 286, 760 286",
  ];
  const particles = Array.from({ length: Math.max(1, Math.min(5, particleCount)) }, (_, index) => index);

  return (
    <div className="hiw-pipeline">
      <div className="hiw-pipeline-track" aria-hidden="true"><span /></div>
      <div className="hiw-pipeline-canvas">
        <svg viewBox="0 0 960 360" preserveAspectRatio="none" aria-hidden="true">
          <defs><filter id="hiw-pipeline-glow"><feGaussianBlur stdDeviation="3" result="blur" /><feMerge><feMergeNode in="blur" /><feMergeNode in="SourceGraphic" /></feMerge></filter></defs>
          {paths.map((path, index) => <g key={index}>
            <path d={path} fill="none" stroke="#686868" strokeWidth="1.3" strokeDasharray="5 8" />
            {!reducedMotion && particles.map((particle) => <circle key={particle} r="3" fill="#eee" filter="url(#hiw-pipeline-glow)"><animateMotion dur={particleSpeed + "s"} begin={(particle * particleSpeed / particles.length + index * .2) + "s"} repeatCount="indefinite" path={path} /></circle>)}
          </g>)}
        </svg>
        <div className="hiw-pipeline-card hiw-pipeline-source"><span className="hiw-node-icon"><Icon name={source.icon} size={18} /></span><strong>{source.title}</strong><small>{source.description}</small></div>
        <div className="hiw-pipeline-card hiw-pipeline-gate"><span className="hiw-node-icon"><Icon name={gate.icon} size={18} /></span><strong>{gate.title}</strong><small>{gate.description}</small><span className="hiw-pipeline-gate-badge">AUTHORITY BOUNDARY</span></div>
        <div className="hiw-pipeline-destinations">
          {destinations.map((destination, index) => <motion.article key={destination.id}
            className={"hiw-pipeline-destination " + (index === activeIndex ? "is-active" : "")}
            animate={reducedMotion ? undefined : { opacity: index === activeIndex ? 1 : .58, x: index === activeIndex ? 0 : 4 }}
            transition={{ duration: .45 }}>
            <span className="hiw-node-icon"><Icon name={destination.icon} size={16} /></span><span><strong>{destination.title}</strong><small>{destination.description}</small></span>
          </motion.article>)}
        </div>
      </div>
      <p className="hiw-diagram-note">The browser is not the authority. Rust validates the request before an API mutation or bot-bridge operation.</p>
    </div>
  );
}
