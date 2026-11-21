
import type { ReactNode } from "react";
import type { IconName } from "./IconRegistry";

const glyphs: Record<IconName, ReactNode> = {
  overview: (
    <>
      <rect x="3.5" y="3.5" width="7" height="7" rx="1" />
      <rect x="13.5" y="3.5" width="7" height="7" rx="1" />
      <rect x="3.5" y="13.5" width="7" height="7" rx="1" />
      <rect x="13.5" y="13.5" width="7" height="7" rx="1" />
    </>
  ),
  commands: (
    <>
      <path d="M8 5 3.5 12 8 19" />
      <path d="m16 5 4.5 7-4.5 7" />
      <path d="m14 3-4 18" />
    </>
  ),
  atlas: (
    <>
      <circle cx="12" cy="12" r="2.5" />
      <circle cx="5" cy="6" r="1.5" />
      <circle cx="19" cy="5" r="1.5" />
      <circle cx="19" cy="19" r="1.5" />
      <circle cx="5" cy="18" r="1.5" />
      <path d="m7 7.2 3.2 3M17 6.5l-3.2 4M17 17.5l-3.2-4M7 17l3.2-3" />
    </>
  ),
  extensions: (
    <>
      <rect x="3.5" y="3.5" width="7" height="7" rx="1" />
      <rect x="13.5" y="3.5" width="7" height="7" rx="1" />
      <rect x="3.5" y="13.5" width="7" height="7" rx="1" />
      <path d="M17 13.5v7M13.5 17h7" />
    </>
  ),
  audit: (
    <>
      <circle cx="12" cy="12" r="8.5" />
      <path d="M12 7v5l3.5 2" />
    </>
  ),
  diagnostics: <path d="M3 13h4l2.2-6 4.2 11 2.2-6H21" />,
  logs: (
    <>
      <path d="M5 6h14M5 12h14M5 18h14" />
      <circle cx="3" cy="6" r=".4" fill="currentColor" stroke="none" />
      <circle cx="3" cy="12" r=".4" fill="currentColor" stroke="none" />
      <circle cx="3" cy="18" r=".4" fill="currentColor" stroke="none" />
    </>
  ),
  integrations: (
    <>
      <path d="M4 8h7M13 8h7M4 16h7M13 16h7" />
      <circle cx="12" cy="8" r="2.5" />
      <circle cx="12" cy="16" r="2.5" />
    </>
  ),
  database: (
    <>
      <ellipse cx="12" cy="5.5" rx="8" ry="3" />
      <path d="M4 5.5v13c0 1.7 3.6 3 8 3s8-1.3 8-3v-13M4 12c0 1.7 3.6 3 8 3s8-1.3 8-3" />
    </>
  ),
  refresh: (
    <>
      <path d="M20 7v5h-5" />
      <path d="M19 12a7 7 0 0 0-12-4.8L5 9M4 17v-5h5" />
      <path d="M5 12a7 7 0 0 0 12 4.8L19 15" />
    </>
  ),
  menu: <path d="M4 6h16M4 12h16M4 18h16" />,
  home: <path d="m3 10 9-7 9 7v10a1 1 0 0 1-1 1h-6v-7h-4v7H4a1 1 0 0 1-1-1z" />,
  retry: (
    <>
      <path d="M20 7v5h-5" />
      <path d="M19 12a7 7 0 1 0 1 4" />
    </>
  ),
  save: (
    <>
      <path d="M5 3h12l4 4v14H3V3z" />
      <path d="M7 3v6h10V3M7 21v-7h10v7" />
    </>
  ),
  reset: (
    <>
      <path d="M3 12a9 9 0 1 0 2.6-6.4L3 8" />
      <path d="M3 3v5h5" />
    </>
  ),
  "shield-check": (
    <>
      <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
      <path d="m8.5 12 2.2 2.2 4.8-4.8" />
    </>
  ),
  shield: <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />,
  upload: (
    <>
      <path d="M12 16V4" />
      <path d="m7 9 5-5 5 5" />
      <path d="M4 17v3h16v-3" />
    </>
  ),
  image: (
    <>
      <rect x="3" y="3" width="18" height="18" rx="2" />
      <circle cx="8.5" cy="8.5" r="1.5" />
      <path d="m21 15-5-5L5 21" />
    </>
  ),
  palette: (
    <>
      <path d="M12 3a9 9 0 1 0 0 18h1.2a2 2 0 0 0 1.5-3.3 1.7 1.7 0 0 1 1.3-2.8H18a3 3 0 0 0 3-3c0-5-4-8.9-9-8.9z" />
      <circle cx="7.5" cy="11" r="1" />
      <circle cx="10" cy="7.5" r="1" />
      <circle cx="15" cy="8" r="1" />
    </>
  ),
  check: <path d="m5 12 4 4L19 6" />,
  "check-circle": (
    <>
      <circle cx="12" cy="12" r="9" />
      <path d="m7.5 12 3 3 6-6" />
    </>
  ),
  "alert-circle": (
    <>
      <circle cx="12" cy="12" r="9" />
      <path d="M12 7.5v5.5M12 16.5h.01" />
    </>
  ),
  search: (
    <>
      <circle cx="10.8" cy="10.8" r="6.8" />
      <path d="m16 16 5 5" />
    </>
  ),
  copy: (
    <>
      <rect x="8" y="8" width="12" height="12" rx="2" />
      <path d="M16 8V6a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v8a2 2 0 0 0 2 2h2" />
    </>
  ),
  activity: <path d="M3 13h4l2.2-6 4.2 11 2.2-6H21" />,
  "arrow-up-right": (
    <>
      <path d="M7 17 17 7" />
      <path d="M8 7h9v9" />
    </>
  ),
  "chevron-right": <path d="m9 18 6-6-6-6" />,
  close: <path d="m18 6-12 12M6 6l12 12" />,
  role: (
    <>
      <circle cx="8" cy="8" r="3" />
      <path d="M2 20v-1a6 6 0 0 1 12 0v1zM16 5.5a3 3 0 0 1 0 5.8M17 14a5 5 0 0 1 5 5v1" />
    </>
  ),
  channel: (
    <>
      <path d="m4 8 16-2M4 16l16-2" />
      <path d="m10 3-2 18M16 3l-2 18" />
    </>
  ),
  lock: (
    <>
      <rect x="4" y="10" width="16" height="11" rx="2" />
      <path d="M8 10V7a4 4 0 1 1 8 0v3M12 14v3" />
    </>
  ),
  server: (
    <>
      <rect x="3" y="3" width="18" height="7" rx="2" />
      <rect x="3" y="14" width="18" height="7" rx="2" />
      <path d="M7 6.5h.01M7 17.5h.01M11 6.5h7M11 17.5h7" />
    </>
  ),
  sparkles: (
    <>
      <path d="m12 3 1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8L12 3z" />
      <path d="m19 15 .8 2.2L22 18l-2.2.8L19 21l-.8-2.2L16 18l2.2-.8L19 15z" />
    </>
  ),
  "external-link": (
    <>
      <path d="M14 4h6v6" />
      <path d="m20 4-9 9" />
      <path d="M18 13v5a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2v-8a2 2 0 0 1 2-2h5" />
    </>
  ),
};

export interface IconProps {
  name: IconName;
  size?: number;
  className?: string;
  animated?: boolean;
}

export function Icon({ name, size = 18, className, animated = true }: IconProps) {
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
      <g className="icon-glyph">{glyphs[name]}</g>
    </svg>
  );
}
