"use client";

import { motion } from "motion/react";
import { useReducedMotion } from "../Hooks/useReducedMotion";

const offsets = [-330, -275, -220, -165, -110, -55, 55, 110, 165, 220, 275, 330];

export function PathFlow() {
  const reducedMotion = useReducedMotion();
  return (
    <div className="hiw-pathflow" aria-hidden="true">
      <svg viewBox="-400 0 1600 520" preserveAspectRatio="xMidYMid meet">
        <defs>
          <linearGradient id="hiw-pathflow-gradient" x1="0" x2="1">
            <stop offset="0" stopColor="#777" stopOpacity=".05" />
            <stop offset=".5" stopColor="#ddd" stopOpacity=".5" />
            <stop offset="1" stopColor="#777" stopOpacity=".05" />
          </linearGradient>
          <filter id="hiw-pathflow-glow"><feGaussianBlur stdDeviation="3" result="blur" /><feMerge><feMergeNode in="blur" /><feMergeNode in="SourceGraphic" /></feMerge></filter>
        </defs>
        {offsets.map((offset, index) => {
          const left = index < 6;
          const d = left
            ? "M " + (400 + offset) + " 12 C " + (480 + offset) + " 180, " + (480 + offset) + " 340, " + (400 + offset) + " 508"
            : "M " + (400 + offset) + " 12 C " + (320 + offset) + " 180, " + (320 + offset) + " 340, " + (400 + offset) + " 508";
          return (
            <g key={offset}>
              <motion.path d={d} fill="none" stroke="url(#hiw-pathflow-gradient)" strokeWidth="1" strokeDasharray="4 9"
                initial={reducedMotion ? false : { pathLength: 0, opacity: 0 }}
                animate={reducedMotion ? { pathLength: 1, opacity: .24 } : { pathLength: 1, opacity: [.12, .42, .12] }}
                transition={reducedMotion ? { duration: 0 } : { pathLength: { duration: 1.5, delay: index * .04 }, opacity: { duration: 5 + index * .2, repeat: Infinity, ease: "easeInOut" } }} />
              {!reducedMotion ? <circle r="3" fill="#ddd" filter="url(#hiw-pathflow-glow)">
                <animateMotion dur={(4 + index * .22) + "s"} repeatCount="indefinite" path={d} />
              </circle> : null}
            </g>
          );
        })}
        <path d="M 400 12 V 508" stroke="#aaa" strokeOpacity=".2" strokeWidth="1.2" />
        {!reducedMotion ? <circle r="4" fill="#fff" filter="url(#hiw-pathflow-glow)"><animateMotion dur="5s" repeatCount="indefinite" path="M 400 12 V 508" /></circle> : null}
      </svg>
    </div>
  );
}
