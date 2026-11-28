export function WebGLFallback() {
  return (
    <svg viewBox="0 0 160 140" width="100%" height="100%" aria-hidden="true">
      <defs><radialGradient id="scene-glow"><stop stopColor="#fff" stopOpacity=".22" /><stop offset="1" stopColor="#fff" stopOpacity="0" /></radialGradient></defs>
      <circle cx="80" cy="70" r="64" fill="url(#scene-glow)" />
      <g fill="none" stroke="currentColor" opacity=".65">
        <ellipse cx="80" cy="70" rx="56" ry="19" transform="rotate(-28 80 70)" />
        <ellipse cx="80" cy="70" rx="56" ry="19" transform="rotate(52 80 70)" />
        <circle cx="80" cy="70" r="25" />
      </g>
      <path d="m80 40 26 30-26 30-26-30z" fill="#fff" fillOpacity=".08" stroke="currentColor" strokeOpacity=".8" />
      <circle cx="80" cy="70" r="3" fill="currentColor" />
    </svg>
  );
}
