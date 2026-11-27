import { Card, AnimatedNumber } from "../../UI";

export function CommandSummary({ enabled, disabled, percent, unavailable }: { enabled: number; disabled: number; percent: number; unavailable: boolean }) {
  return (
    <Card eyebrow="EFFECTIVE CONFIGURATION" title="Command access">
      <div className="distribution-label"><strong>{unavailable ? "—" : <AnimatedNumber value={percent} suffix="%" />}</strong><span>of managed commands enabled</span></div>
      <svg className="distribution-track" viewBox="0 0 100 6" role="img" aria-label="Share of managed commands enabled">
        <rect className="distribution-track-bg" width="100" height="6" rx="3" />
        <rect className="distribution-track-fill" width={unavailable ? 0 : percent} height="6" rx="3" />
      </svg>
      <div className="distribution-meta"><span>Enabled {unavailable ? "—" : <AnimatedNumber value={enabled} />}</span><span>Disabled {unavailable ? "—" : <AnimatedNumber value={disabled} />}</span></div>
    </Card>
  );
}
