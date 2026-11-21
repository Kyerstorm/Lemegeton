"use client";

import { useState } from "react";
import { Icon } from "../Icons";

export interface PolicyConsent {
  accepted: boolean;
  versions: { terms: string; privacy: string; guidelines: string };
  policies: { label: string; url: string }[];
}
export interface PolicyConsentGateProps {
  consent: PolicyConsent | null;
  saving: boolean;
  error: string;
  onRetry: () => void;
  onAccept: () => void;
  onDecline: () => void;
}

export function PolicyConsentGate({
  consent,
  saving,
  error,
  onRetry,
  onAccept,
  onDecline,
}: PolicyConsentGateProps) {
  const [checked, setChecked] = useState({ terms: false, privacy: false, guidelines: false });
  const complete = checked.terms && checked.privacy && checked.guidelines;
  const items = [
    { key: "terms" as const, label: "Terms of Service", version: consent?.versions.terms },
    { key: "privacy" as const, label: "Privacy Policy", version: consent?.versions.privacy },
    { key: "guidelines" as const, label: "Community Guidelines", version: consent?.versions.guidelines },
  ];

  return (
    <main className="policy-gate">
      <section className="policy-gate-card" aria-labelledby="policy-gate-title">
        <a className="brand policy-brand" href="/" aria-label="Lemegeton dashboard">
          <span className="brand-mark"><img src="/brand/lemegeton.svg" alt="" width={30} height={30} /></span>
          <span className="brand-copy"><strong>LEMEGETON</strong><small>CONTROL PLANE</small></span>
        </a>
        <div className="policy-kicker"><span className="signal-dot" /> ACCOUNT / POLICY REVIEW</div>
        <h1 id="policy-gate-title">Before you<br /><span>step inside.</span></h1>
        <p className="policy-intro">Please review the current Lemegeton policies. We record your Discord account, the policy versions you accept, and the acceptance time.</p>

        {consent ? <>
          <div className="policy-links">
            {consent.policies.map(policy => (
              <a key={policy.label} href={policy.url} target="_blank" rel="noopener noreferrer">
                <span>{policy.label}</span><Icon name="home" size={14} />
              </a>
            ))}
          </div>
          <div className="policy-checklist" aria-label="Policy acceptance">
            {items.map(item => (
              <label className="policy-check" key={item.key}>
                <input
                  type="checkbox"
                  checked={checked[item.key]}
                  onChange={event => setChecked(current => ({ ...current, [item.key]: event.target.checked }))}
                />
                <span className="policy-checkmark" aria-hidden="true"><Icon name="check" size={13} /></span>
                <span className="policy-check-copy">
                  <strong>I have read and agree to the {item.label}</strong>
                  <small>CURRENT VERSION / {item.version}</small>
                </span>
              </label>
            ))}
          </div>
          <button className="policy-accept" type="button" disabled={!complete || saving} onClick={onAccept}>
            <Icon name="shield-check" size={16} />{saving ? "Recording agreement…" : "Agree and continue"}
          </button>
          <p className="policy-note">Declining keeps dashboard features locked. You can sign out without accepting.</p>
        </> : <>
          <div className="policy-unavailable" role="alert">
            <strong>We couldn't verify the current policy versions.</strong>
            <span>{error || "Dashboard access stays locked until verification succeeds."}</span>
          </div>
          <button className="policy-accept" type="button" disabled={saving} onClick={onRetry}>
            <Icon name="refresh" size={16} />Try again
          </button>
        </>}
        {error && consent ? <p className="policy-error" role="alert">{error}</p> : null}
        <button className="policy-decline" type="button" onClick={onDecline}>Decline and sign out</button>
        <div className="policy-foot"><span>LEMEGETON / POLICY GATE</span><span>NO ACCESS UNTIL VERIFIED</span></div>
      </section>
    </main>
  );
}
