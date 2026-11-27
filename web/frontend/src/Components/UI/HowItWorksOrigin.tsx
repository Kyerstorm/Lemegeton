"use client";

import type { ReactNode } from "react";
import { motion } from "motion/react";
import { Icon, type IconName } from "../Icons";
import { useReducedMotion } from "../Hooks/useReducedMotion";

export interface OriginNode {
  id: string;
  title: string;
  detail: string;
  icon: IconName;
}
export interface OriginProps {
  topTitle?: string;
  topDetail?: string;
  topIcon?: ReactNode;
  bottomNodes?: OriginNode[];
  curve?: number;
  particleSpeed?: number;
  particleColor?: string;
  curveColor?: string;
}

const bottomDefaults: OriginNode[] = [
  { id: "providers", title: "Provider helpers", detail: "Source-specific requests", icon: "integrations" },
  { id: "commands", title: "Command services", detail: "Reusable domain operations", icon: "commands" },
  { id: "libsql", title: "libSQL", detail: "Structured records and metadata", icon: "database" },
  { id: "objects", title: "RocksDB", detail: "Private binary objects", icon: "server" },
];

export function Origin({
  topTitle = "Lemegeton runtime",
  topDetail = "One Discord.js client",
  topIcon,
  bottomNodes = bottomDefaults,
  curve = 90,
  particleSpeed = 3.2,
  particleColor = "#eee",
  curveColor = "#676767",
}: OriginProps) {
  const reducedMotion = useReducedMotion();
  const positions = [180, 370, 570, 760, 850].slice(0, bottomNodes.length);
  const x = positions.length === 1 ? [470] : positions;
  const makePath = (endX: number) => "M 470 116 C 470 " + (116 + curve) + ", " + endX + " " + (310 - curve) + ", " + endX + " 310";

  return (
    <div className="hiw-origin">
      <div className="hiw-origin-root">
        <span className="hiw-origin-root-icon">{topIcon ?? <Icon name="activity" size={22} />}</span>
        <strong>{topTitle}</strong><small>{topDetail}</small>
      </div>
      <svg viewBox="0 0 940 390" preserveAspectRatio="none" aria-hidden="true">
        <defs><filter id="hiw-origin-glow"><feGaussianBlur stdDeviation="2" result="blur" /><feMerge><feMergeNode in="blur" /><feMergeNode in="SourceGraphic" /></feMerge></filter></defs>
        {bottomNodes.map((node, index) => {
          const d = makePath(x[index]);
          return <g key={node.id}>
            <motion.path d={d} fill="none" stroke={curveColor} strokeWidth="1.25" strokeDasharray="4 7"
              initial={reducedMotion ? false : { pathLength: 0 }} animate={{ pathLength: 1 }}
              transition={{ duration: reducedMotion ? 0 : 1.2, delay: reducedMotion ? 0 : index * .1 }} />
            {!reducedMotion ? <circle r="3" fill={particleColor} filter="url(#hiw-origin-glow)"><animateMotion dur={particleSpeed + "s"} repeatCount="indefinite" path={d} begin={(index * .25) + "s"} /></circle> : null}
          </g>;
        })}
      </svg>
      <div className="hiw-origin-nodes">
        {bottomNodes.map((node, index) => <motion.article key={node.id} className="hiw-origin-node"
          initial={reducedMotion ? false : { opacity: 0, y: 12 }} whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, amount: .25 }} transition={{ duration: reducedMotion ? 0 : .45, delay: reducedMotion ? 0 : index * .06 }}>
          <span className="hiw-node-icon"><Icon name={node.icon} size={18} /></span>
          <strong>{node.title}</strong><small>{node.detail}</small>
        </motion.article>)}
      </div>
    </div>
  );
}
