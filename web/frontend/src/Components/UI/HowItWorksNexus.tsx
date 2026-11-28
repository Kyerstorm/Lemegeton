"use client";

import { motion } from "motion/react";
import { Icon, type IconName } from "../Icons";
import { GlowEffect } from "./GlowEffect";
import { useReducedMotion } from "../Hooks/useReducedMotion";

export interface NexusNode {
  id: string;
  label: string;
  detail?: string;
  icon: IconName;
}
export interface NexusProps {
  nodes?: NexusNode[];
  centerTitle?: string;
  centerDetail?: string;
  curve?: number;
  particleSpeed?: number;
}

const nodeDefaults: NexusNode[] = [
  { id: "media", label: "Media records", detail: "Provider IDs and metadata", icon: "search" },
  { id: "creators", label: "Creators", detail: "People and credits", icon: "home" },
  { id: "franchises", label: "Franchises", detail: "Source-declared links", icon: "archive" },
  { id: "adaptations", label: "Adaptations", detail: "Evidence-backed relations", icon: "integrations" },
  { id: "community", label: "Community", detail: "Reviewed contributions", icon: "activity" },
  { id: "sources", label: "Sources", detail: "Provenance and evidence", icon: "shield-check" },
];

export function Nexus({
  nodes = nodeDefaults,
  centerTitle = "Knowledge Atlas",
  centerDetail = "inside /discover",
  curve = 70,
  particleSpeed = 4,
}: NexusProps) {
  const reducedMotion = useReducedMotion();
  const positions = [
    { x: 18, y: 22 }, { x: 50, y: 12 }, { x: 82, y: 22 },
    { x: 18, y: 78 }, { x: 50, y: 88 }, { x: 82, y: 78 },
  ];

  return (
    <div className="hiw-nexus">
      <svg viewBox="0 0 1000 560" preserveAspectRatio="none" aria-hidden="true">
        <defs><filter id="hiw-nexus-glow"><feGaussianBlur stdDeviation="3" result="blur" /><feMerge><feMergeNode in="blur" /><feMergeNode in="SourceGraphic" /></feMerge></filter></defs>
        {nodes.map((node, index) => {
          const point = positions[index % positions.length];
          const controlX = point.x < 50 ? 500 - curve : 500 + curve;
          const d = "M " + (point.x * 10) + " " + (point.y * 5.6) + " Q " + controlX + " 280 500 280";
          return <g key={node.id}>
            <motion.path d={d} fill="none" stroke="#888" strokeWidth="1.2" strokeDasharray="4 8"
              animate={reducedMotion ? { opacity: .3 } : { strokeDashoffset: [0, -70], opacity: [.15, .55, .15] }}
              transition={reducedMotion ? { duration: 0 } : { duration: 8 + index, repeat: Infinity, ease: "linear" }} />
            {!reducedMotion ? <circle r="3" fill="#eee" filter="url(#hiw-nexus-glow)"><animateMotion dur={(particleSpeed + index * .35) + "s"} repeatCount="indefinite" path={d} begin={(index * .32) + "s"} /></circle> : null}
          </g>;
        })}
      </svg>
      {nodes.map((node, index) => {
        const point = positions[index % positions.length];
        return <motion.div key={node.id} className="hiw-nexus-node"
          style={{ left: point.x + "%", top: point.y + "%" }}
          animate={reducedMotion ? undefined : { y: [0, -4, 0] }}
          transition={reducedMotion ? undefined : { duration: 3 + index * .2, repeat: Infinity, ease: "easeInOut" }}>
          <span className="hiw-node-icon"><Icon name={node.icon} size={16} /></span>
          <strong>{node.label}</strong>
          {node.detail ? <small>{node.detail}</small> : null}
        </motion.div>;
      })}
      <div className="hiw-nexus-center">
        <GlowEffect className="hiw-glow-layer" colors={["#fff", "#555", "#fff"]} mode="pulse" blur="medium" duration={5} />
        <span className="hiw-nexus-center-icon"><Icon name="search" size={22} /></span>
        <strong>{centerTitle}</strong><small>{centerDetail}</small>
      </div>
    </div>
  );
}
