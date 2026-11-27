"use client";

import { motion } from "motion/react";
import { Icon, type IconName } from "../Icons";
import { useReducedMotion } from "../Hooks/useReducedMotion";

export interface BranchFlowNode {
  id: string;
  label: string;
  description: string;
  icon: IconName;
}
export interface BranchFlowProps {
  nodes?: BranchFlowNode[];
  curve?: number;
  particleSpeed?: number;
  particleColor?: string;
  curveColor?: string;
}

const defaultNodes: BranchFlowNode[] = [
  { id: "discover", label: "/discover", description: "Search and media intelligence", icon: "search" },
  { id: "archive", label: "/archive", description: "Shared archives and collections", icon: "archive" },
  { id: "community", label: "/community", description: "Activities, rankings and sessions", icon: "activity" },
  { id: "play", label: "/play", description: "Group games and quizzes", icon: "sparkles" },
  { id: "profile", label: "/profile", description: "Profiles and provider links", icon: "home" },
  { id: "custom-role", label: "/custom-role", description: "Member role tools", icon: "role" },
  { id: "music", label: "/music", description: "Artist and release discovery", icon: "integrations" },
  { id: "settings", label: "/settings", description: "Server configuration", icon: "settings" },
];

export function BranchFlow({
  nodes = defaultNodes,
  curve = 95,
  particleSpeed = 3.6,
  particleColor = "#ededed",
  curveColor = "#555",
}: BranchFlowProps) {
  const reducedMotion = useReducedMotion();
  const width = 1120;
  const centerX = width / 2;
  const columns = Math.max(1, nodes.length);
  const nodeWidth = Math.min(118, 1000 / columns - 10);
  const startX = centerX - ((columns - 1) * (1000 / columns)) / 2;
  const positions = nodes.map((_, index) => startX + index * (1000 / columns));

  return (
    <div className="hiw-branch">
      <div className="hiw-branch-root"><span className="hiw-node-icon"><Icon name="commands" size={18} /></span><span><strong>src/registry.ts</strong><small>Command registration and dispatch</small></span></div>
      <svg viewBox={"0 0 " + width + " 370"} preserveAspectRatio="none" aria-hidden="true">
        <defs><filter id="hiw-branch-glow"><feGaussianBlur stdDeviation="2.4" result="blur" /><feMerge><feMergeNode in="blur" /><feMergeNode in="SourceGraphic" /></feMerge></filter></defs>
        {positions.map((x, index) => {
          const d = "M " + centerX + " 12 C " + centerX + " " + (70 + curve) + ", " + x + " " + (105 + curve) + ", " + x + " 342";
          return <g key={nodes[index].id}>
            <motion.path d={d} stroke={curveColor} strokeWidth="1.25" fill="none" strokeDasharray="4 7"
              initial={reducedMotion ? false : { pathLength: 0 }} animate={{ pathLength: 1 }}
              transition={{ duration: reducedMotion ? 0 : 1.1, delay: reducedMotion ? 0 : index * .06 }} />
            {!reducedMotion ? <circle r="3" fill={particleColor} filter="url(#hiw-branch-glow)"><animateMotion dur={particleSpeed + "s"} repeatCount="indefinite" path={d} begin={(index * .2) + "s"} /></circle> : null}
          </g>;
        })}
      </svg>
      <div className="hiw-branch-grid" style={{ gridTemplateColumns: "repeat(" + nodes.length + ", minmax(" + nodeWidth + "px, 1fr))" }}>
        {nodes.map((node) => <article className="hiw-branch-node" key={node.id}><span className="hiw-branch-node-icon"><Icon name={node.icon} size={15} /></span><strong>{node.label}</strong><small>{node.description}</small></article>)}
      </div>
      <p className="hiw-diagram-note">Feature commands group related actions. /help, /privacy, /feedback and required setup commands remain separate.</p>
    </div>
  );
}
