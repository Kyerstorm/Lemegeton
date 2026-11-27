"use client";

import type { CSSProperties } from "react";

const DEFAULT_SIGNATURE_PATH =
  "M126.4 164.1 C166.4 156.1 259 148.8 283 148.8 C324.3 150 299 276.7 295.5 324.1 C289.2 368.9 262.9 382.1 233.3 337.2 C213.9 310 221.2 240 360.2 244.9 C362 288.1 349.3 387.5 344.7 458.2 C344.7 458.2 348.9 289.8 382.8 245.7 C404.5 222.9 450.3 223.3 442.3 269.4 C414.9 328.6 344.9 333.4 316.2 334.3 C340.2 334.3 547.2 320.3 571.2 320.3";
const DEFAULT_SIGNATURE_EASING = "cubic-bezier(0.2, 0.2, 0.8, 0.9)";

export type SignatureProps = {
  word?: string;
  path?: string;
  viewBox?: string;
  size?: number | string;
  strokeWidth?: number;
  duration?: number | string;
  delay?: number | string;
  easing?: string;
  className?: string;
  ariaLabel?: string;
};

function toCssTime(value: number | string): string {
  return typeof value === "number" ? `${value}s` : value;
}

export function Signature({
  word = "Lemegeton",
  path,
  viewBox,
  size = "100%",
  strokeWidth = 10,
  duration = 2.8,
  delay = 0,
  easing = DEFAULT_SIGNATURE_EASING,
  className,
  ariaLabel,
}: SignatureProps) {
  const width = typeof size === "number" ? `${size}px` : size;
  const style: CSSProperties = { width, height: "auto" };
  const animationStyle: CSSProperties = {
    animationDelay: toCssTime(delay),
    animationDuration: toCssTime(duration),
    animationTimingFunction: easing,
    animationFillMode: "forwards",
  };

  return (
    <svg
      aria-hidden={ariaLabel ? undefined : true}
      aria-label={ariaLabel}
      className={["block overflow-visible", className].filter(Boolean).join(" ")}
      role={ariaLabel ? "img" : undefined}
      style={style}
      viewBox={viewBox ?? (path ? "0 0 900 460" : "0 0 820 160")}
    >
      {path ? (
        <path
          className="dqnamo-signature-stroke"
          d={path}
          pathLength={1}
          style={{ ...animationStyle, strokeWidth }}
        />
      ) : (
        <text
          className="dqnamo-signature-word"
          x="18"
          y="118"
          fontSize="110"
          textLength="780"
          lengthAdjust="spacingAndGlyphs"
          style={animationStyle}
        >
          {word}
        </text>
      )}
    </svg>
  );
}
