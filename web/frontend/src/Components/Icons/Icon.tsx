import { ICON_GLYPHS } from "./IconGlyphs";
import type { IconName } from "./IconRegistry";

export interface IconProps {
  name: IconName;
  size?: number;
  className?: string;
  animated?: boolean;
}

export function Icon({ name, size = 18, className, animated = true }: IconProps) {
  const Glyph = ICON_GLYPHS[name];
  const classes = [
    "icon-svg",
    `icon-${name}`,
    animated ? "icon-animated" : "",
    className,
  ].filter(Boolean).join(" ");

  return (
    <svg
      aria-hidden="true"
      className={classes}
      data-icon={name}
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.7"
      strokeLinecap="round"
      strokeLinejoin="round"
      focusable="false"
    >
      <g className="icon-glyph"><Glyph /></g>
    </svg>
  );
}
