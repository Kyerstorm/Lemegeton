"use client";

import type { ReactNode } from "react";
import { motion } from "motion/react";
import { Icon, type IconName } from "../Icons";
import { BrandMark } from "../Brand/BrandMark";
import { GlowEffect } from "./GlowEffect";
import { useReducedMotion } from "../Hooks/useReducedMotion";

export interface DataFlowNode {
  id: string;
  title: string;
  detail: string;
  icon: IconName;
}

export interface DataFlowProps {
  leftNodes?: DataFlowNode[];
  rightNodes?: DataFlowNode[];
  centerIcon?: ReactNode;
  centerTitle?: string;
  centerDetail?: string;
  leftGap?: number;
  rightGap?: number;
  pathColor?: string;
  particleColor?: string;
  particleSpeed?: number;
  pathWidth?: number;
  particleSize?: number;
}

const defaultLeft: DataFlowNode[] = [
  { id: "gateway", title: "Discord gateway", detail: "Commands, buttons and events", icon: "activity" },
  { id: "workers", title: "Background workers", detail: "Scheduled runtime tasks", icon: "refresh" },
  { id: "dashboard", title: "Dashboard bridge", detail: "Approved bot-side operations", icon: "shield-check" },
];
const defaultRight: DataFlowNode[] = [
  { id: "providers", title: "Provider adapters", detail: "External media metadata", icon: "integrations" },
  { id: "libsql", title: "Shared libSQL", detail: "Structured records and state", icon: "database" },
  { id: "rocksdb", title: "RocksDB objects", detail: "Private binary objects", icon: "server" },
];

export function DataFlow({
  leftNodes = defaultLeft,
  rightNodes = defaultRight,
  centerIcon,
  centerTitle = "Lemegeton runtime",
  centerDetail = "TypeScript · discord.js",
  leftGap = 30,
  rightGap = 30,
  pathColor = "#777",
  particleColor = "#ededed",
  particleSpeed = 4,
  pathWidth = 1.5,
  particleSize = 3.5,
}: DataFlowProps) {
  const reducedMotion = useReducedMotion();
  const leftY = (index: number) => 250 + (index - (leftNodes.length - 1) / 2) * (leftGap * 3.2);
  const rightY = (index: number) => 250 + (index - (rightNodes.length - 1) / 2) * (rightGap * 3.2);
  const path = (startY: number, reverse = false) => reverse
    ? "M 530 250 C 625 250, 625 " + startY + ", 730 " + startY
    : "M 270 " + startY + " C 365 " + startY + ", 365 250, 470 250";

  return (
    <div className="hiw-data-diagram">
      <svg viewBox="0 0 1000 500" preserveAspectRatio="none" aria-hidden="true">
        <defs>
          <linearGradient id="hiw-dataflow-line" x1="0" x2="1"><stop offset="0" stopColor={pathColor} stopOpacity=".08" /><stop offset=".5" stopColor="#dedede" stopOpacity=".7" /><stop offset="1" stopColor={pathColor} stopOpacity=".08" /></linearGradient>
          <filter id="hiw-dataflow-glow"><feGaussianBlur stdDeviation="3" result="blur" /><feMerge><feMergeNode in="blur" /><feMergeNode in="SourceGraphic" /></feMerge></filter>
        </defs>
        {leftNodes.map((node, index) => {
          const d = path(leftY(index));
          return <g key={node.id}>
            <motion.path d={d} fill="none" stroke="url(#hiw-dataflow-line)" strokeWidth={pathWidth} strokeDasharray="5 8"
              initial={reducedMotion ? false : { pathLength: 0 }} animate={{ pathLength: 1 }}
              transition={{ duration: reducedMotion ? 0 : 1.2, delay: reducedMotion ? 0 : index * .12 }} />
            {!reducedMotion ? <circle r={particleSize} fill={particleColor} filter="url(#hiw-dataflow-glow)"><animateMotion dur={particleSpeed + "s"} repeatCount="indefinite" path={d} begin={(index * .28) + "s"} /></circle> : null}
          </g>;
        })}
        {rightNodes.map((node, index) => {
          const d = path(rightY(index), true);
          return <g key={node.id}>
            <motion.path d={d} fill="none" stroke="url(#hiw-dataflow-line)" strokeWidth={pathWidth} strokeDasharray="5 8"
              initial={reducedMotion ? false : { pathLength: 0 }} animate={{ pathLength: 1 }}
              transition={{ duration: reducedMotion ? 0 : 1.2, delay: reducedMotion ? 0 : .35 + index * .12 }} />
            {!reducedMotion ? <circle r={particleSize} fill={particleColor} filter="url(#hiw-dataflow-glow)"><animateMotion dur={particleSpeed + "s"} repeatCount="indefinite" path={d} begin={(index * .31) + "s"} /></circle> : null}
          </g>;
        })}
      </svg>
      <div className="hiw-data-side">
        {leftNodes.map((node) => <div className="hiw-flow-node" key={node.id}><span className="hiw-node-icon"><Icon name={node.icon} size={16} /></span><span><strong>{node.title}</strong><small>{node.detail}</small></span></div>)}
      </div>
      <div className="hiw-data-core">
        <GlowEffect className="hiw-glow-layer" colors={["#fff", "#555", "#fff"]} mode="rotate" blur="strong" duration={18} />
        <div className="hiw-core-mark">{centerIcon ?? <BrandMark size={30} />}</div>
        <strong>{centerTitle}</strong>
        <small>{centerDetail}</small>
        <span className="hiw-core-caption">ONE RUNTIME · MULTIPLE GUILDS</span>
      </div>
      <div className="hiw-data-side">
        {rightNodes.map((node) => <div className="hiw-flow-node" key={node.id}><span className="hiw-node-icon"><Icon name={node.icon} size={16} /></span><span><strong>{node.title}</strong><small>{node.detail}</small></span></div>)}
      </div>
      <p className="hiw-diagram-note">Conceptual flow. Each operation uses only the provider, database or object-store path it needs.</p>
    </div>
  );
}
