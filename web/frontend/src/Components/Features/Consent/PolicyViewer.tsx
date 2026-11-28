import type { DashboardConsent } from "../../../Types/dashboard";
import { Icon } from "../../Icons";

export function PolicyViewer({ consent }: { consent: DashboardConsent | null }) {
  if (!consent) return null;
  return (
    <div className="policy-links">
      {consent.policies.map(policy => (
        <a key={policy.label} href={policy.url} target="_blank" rel="noopener noreferrer">
          <span>{policy.label}</span><Icon name="external-link" size={14} />
        </a>
      ))}
    </div>
  );
}
